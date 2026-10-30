# Peer 后端原型：构建与接入

当前可用的是 **Linux 本机两端**原型：可选原生 WebRTC helper、双方 Ed25519 通道绑定认证、
能力协商，以及授权项目的目录、分页读取和格式 15 原子编辑回执。接口契约见
[stk.peer/1](specs/stk-peer-1.md)，helper 的依赖与许可见
[原生模块说明](../desktop/engine/lib/stk_peer/README.md)。

这还不是完整 S4 或跨平台产品。配对界面、持久私钥管理、部署信令、实际 STUN/TURN 中继、
端口预测、项目文件传输、远程桌面控制和 Flower 尚未交付验收。
Python 3.11/3.12/3.14 测试通过不等于 macOS/Windows 或跨机器网络通过。
Peer 独立于本地 stdio 桥和 Linux Runtime，不改变 Runtime 的 Linux、loopback/SSH 边界。

## 准备 Python 与显式 helper

在源码根目录、独立 Python 环境中安装 `python -m pip install '.[peer]'`。
`peer` extra 安装 cryptography；Python 包不携带 helper、原生网络库或自动安装器。

单独准备 libdatachannel **0.24.6**（`USE_NICE=ON`、`NO_MEDIA=ON`、`NO_WEBSOCKET=ON`）、
libnice、OpenSSL 3 及其运行依赖，再构建独立 C++20 目标：

```sh
cmake -S desktop/engine/lib/stk_peer -B /absolute/path/peer-build \
  -DCMAKE_PREFIX_PATH=/absolute/path/dependency-install
cmake --build /absolute/path/peer-build --target stk-peer-transport
```

以上路径须替换为自己的构建与依赖目录。该目标不链接 Blender/GPU，不下载上游依赖，
没有安装规则；后续发行还须处理运行库闭包与第三方许可。

**当前开发 helper 需要显式动态库搜索路径，并非可独立搬走的发行文件。**
本次 Linux 验证使用 `transport/install/lib` 和 `transport/deps/usr/lib/x86_64-linux-gnu`
两类目录；省略后者曾因找不到 `libnice.so.10` 而在协议启动前退出 127。
按自己实际的依赖布局配置启动 Python 的环境，例如：

```sh
export STK_PEER_HELPER=/absolute/path/peer-build/stk-peer-transport
export LD_LIBRARY_PATH=/absolute/path/dependency-install/lib:/absolute/path/dependency-sysroot/usr/lib/x86_64-linux-gnu
ldd "$STK_PEER_HELPER"
```

先解决 `ldd` 中的缺库项，再运行下面的 Python。helper 路径由本机显式传入，
其子进程继承此运行环境。不要用缺库失败判断认证或 ICE 是否正常。

## 本机所有者先建立信任与授权

以下变量由本机配置和已有签名服务提供：`owner_a`/`owner_b` 是重开时保持不变的规范 UUID；
`public_a`/`public_b` 是原始 32 字节公钥；`sign_a`/`sign_b` 是
`sign(message: bytes) -> bytes` 回调，返回 64 字节 Ed25519 签名。
示例不生成、读取、打印或持久化私钥。双方先通过可信渠道核对公钥指纹与 owner UUID；
不能把收到的 hello、SDP 或自报 owner 当作可信 pin。

```python
from suan.peer.authority import PeerAuthority, peer_id_for

authority_a = PeerAuthority(state_a, owner_id=owner_a)
authority_b = PeerAuthority(state_b, owner_id=owner_b)
# 仅在所有者已经核对上述公开身份之后批准；双方认证都需要批准。
authority_a.approve_peer(peer_id_for(public_b), public_b)
authority_b.approve_peer(peer_id_for(public_a), public_a)

# 示例只允许 B 访问 A 的一个既有项目；反方向无需授予项目权限。
bound = authority_a.bind_project(local_project_directory_a)
grant = authority_a.grant(peer_id_for(public_b), bound["project_id"],
                          ["project.read", "project.edit"])
target_a = {"project_id": bound["project_id"], **grant}
```

`state_a`/`state_b` 是本机私有授权目录，必须位于共享项目之外。
`target_a` 只有公开目标元数据 `project_id`、`grant_id`、`database_generation`，可交给已授权的 B。
路径绑定、批准、授权、撤销与重新绑定属于本机所有者 API，不是远端请求方法。
新建项目默认格式 15；旧库使用编辑回执前须由所有者明确备份升级，打开和连接不会自动升级。

## 本机两端连接：信令留在内存，双方并发 start

下例在一个 Python 进程中运行两个 helper，仅演示本机接入；线程原样转发临时信令，
不实现部署信令服务，也不配置外部 STUN/TURN。不要打印或保存 `TransportSignal.payload`、SDP、
ICE 凭据或私钥。`helper_path` 使用上面已准备好运行库的绝对路径。

```python
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import threading
from suan.peer.endpoint import PeerEndpoint
from suan.peer.transport import NativeTransport, TransportError

@contextmanager
def local_pair(helper_path):
    ta = NativeTransport(helper_path, offerer=True, route="udp")
    tb = NativeTransport(helper_path, offerer=False, route="udp")
    a = PeerEndpoint(ta, authority_a, public_key=public_a, sign=sign_a,
                     remote_peer_id=peer_id_for(public_b), remote_owner_id=owner_b)
    b = PeerEndpoint(tb, authority_b, public_key=public_b, sign=sign_b,
                     remote_peer_id=peer_id_for(public_a), remote_owner_id=owner_a)
    stop, pumps = threading.Event(), []
    def forward(source, destination):
        while not stop.is_set():
            try:
                destination.accept_signal(source.next_signal(timeout=.2))
            except TimeoutError:
                continue
            except TransportError:
                stop.set()
                return
    try:
        ta.start()
        tb.start()
        for source, destination in ((ta, tb), (tb, ta)):
            pump = threading.Thread(target=forward, args=(source, destination), daemon=True)
            pumps.append(pump)
            pump.start()
        ta.wait_ready(timeout=15)
        tb.wait_ready(timeout=15)
        with ThreadPoolExecutor(max_workers=2) as pool:
            starts = [pool.submit(endpoint.start, timeout=15) for endpoint in (a, b)]
            for started in starts:
                started.result(timeout=16)
        yield a, b
    finally:
        stop.set()
        a.close()
        b.close()
        ta.close()
        tb.close()
        for pump in pumps:
            pump.join(timeout=1)
```

`NativeTransport.start()` 只启动明确指定的 helper。`PeerEndpoint.start()` 要等双方证明、
确认和自身 hello 回复完成；签名前会核对自己的 peer 身份、已 pin 的远端 owner 和当前通道绑定。
业务请求在本机协商完成前返回 `busy`。`endpoint.capabilities` 是远端可提供方法的副本，
每次项目请求仍检查当前 grant、认证上下文和数据库代次。双方能力与项目授权分别计算。

## 目录、读表与一次编辑

只使用已协商的方法。下面以 B 访问 A 为例；编辑前由调用方保留完整 `original`、
`operation_id` 和原修订，避免丢回复后失去查询身份。

```python
from uuid import uuid4

with local_pair(helper_path) as (a, b):
    catalog = b.request("project.catalog", target_a)
    original = {**target_a, "operation_id": str(uuid4()),
                "expected_revision": catalog["project"]["revision"],
                "commands": [{"op": "create_table", "name": "Peer example"}]}
    # 先由本机调用方保留 original，再明确发送；此处省略宿主自己的保存机制。
    result = b.request("project.edit_operations.apply_once", original)
    receipt = result["receipt"]
    table_id = receipt["commands"][0]["id"]  # 实际生成的稳定 UUID
    page = b.request("project.table.read", {**target_a, "table_id": table_id,
                     "expected_revision": receipt["applied_revision"], "limit": 200})
    saved = b.request("project.edit_operations.get", {**target_a,
                      "operation_id": original["operation_id"]})["receipt"]
```

没有远端 `project.open(directory)`、普通 `project.apply` 或任意脚本执行。
请求不能传本地 handle、路径、scope、owner/caller；回执 scope 由可信授权层绑定。
读页需要明确修订；并发编辑导致 `conflict` 时，重新检查项目状态，不能只替换原写请求的修订。
控制消息上限 16 MiB，原编辑请求 256 KiB/1000 条命令、回执 512 KiB；分页仍受共享读服务预算限制。

## 超时、断线与回执恢复

`request` 只发送一次。超时或断线关闭该一次性连接，不自动重连、重新认证或重放写入。
收到 `PeerCallUncertain`（`suan.peer.endpoint`）时，编辑可能已经提交；关闭连接也不撤销已接受的操作。
提交后的授权登记收尾或结果编码失败同样可能留下不确定结果。

1. 保留原 `operation_id`、`expected_revision`、完整 commands 和目标元数据。
2. 显式新建 transport/endpoint，重新完成认证与协商，使用仍有效的 grant 和同一数据库代次。
3. 调用上面的 `project.edit_operations.get` 查询原 UUID。成功时采用原回执及其中的生成 UUID；
   不再创建另一份编辑。`not_found`、`forbidden`、`unsupported` 等结果须结合所有者状态检查，不能自动换 ID 或 CAS。

只有调用方明确选择重复完全相同的原请求时，才使用原身份调用 `apply_once`；端点不会代做。
撤销 grant/peer 或重新绑定数据库会拒绝旧访问。备份回退、数据库副本和授权状态丢失不提供跨代次全局恰好一次保证。
空闲 UDP 对端关闭也可能要到下一次有限超时请求才被观察到。

验证入口是 `tests/test_peer_authority.py`、`test_peer_projects.py`、`test_peer_protocol.py`，
以及显式设置 `STK_PEER_TEST_HELPER` 后的 `test_peer_endpoint.py`、`test_peer_transport.py`。
测试必须清空 `STK_TOKEN_PLAN_API_KEY` 并移除 `STK_TOKEN_PLAN_MODEL`；原生测试还需要上述运行库环境。
未提供 helper 的跳过不算原生验收；提供的 helper 缺失或不可运行应作为失败处理。
