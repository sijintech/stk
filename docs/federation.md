# 联邦后端：授权、节点训练与隔离聚合

当前有模型／权重差校验、逐数据集逐run本机授权、更新审计和显式单次发送，
以及固定ClientApp/Runtime训练、STK出站WSS与专用blob、持久协调轮次和独立Flower聚合。
[契约](specs/stk-federation-1.md)规定字段、额度与恢复。本机三个独立Runtime的真实TCP/WSS多轮
已验，桌面授权/审计与模型准入、跨站部署和完整S4仍待完成。
读取、重开或恢复不会训练、发送或登记模型。

## 独立算法环境

用独立Linux Python3.12安装基础STK与`suan/federation/requirements-flower.txt`的精确依赖，
即`flwr==1.42.0`、`numpy==2.5.4`。不要在公网hub装flwr，也不要在算法环境装STK的control extra。
该聚合适配器不需要Torch、Ray或Flower服务，使用两项版本绑定的内部辅助接口；升级须重新验证。
`FlowerAggregator`接收明确的Python路径，构造不启动；`aggregate`才启动一次有限聚合。
遥测与更新检查在导入前关闭。结果只是候选，仍须独立评估、明确准入与登记。

## 本机所有者授权

变量来自本机核实的身份、冻结数据／模型定义和有序参数布局，不能从收到的消息倒推expected值。
注册表根目录位于共享项目之外；本地dataset UUID不含路径。不会改变合作方待确认的数据格式，
也不把公开标签作为训练／外发许可。

```python
from suan.federation.consent import ConsentRegistry

registry = ConsentRegistry(private_node_state)
grant = registry.grant(run_id, coordinator_id=verified_coordinator,
    participant_id=verified_node, dataset_id=local_dataset_id,
    dataset_sha256=frozen_dataset_sha256, spec_sha256=frozen_spec_sha256,
    model_layout=approved_parameter_layout, max_rounds=6)
```

授权固定接收方、参与者、run、数据与模型／训练定义摘要，以及名称、顺序、dtype、shape。
只有自报spec摘要不足以允许发送任意数组。实际训练前仍须核对冻结字节和当前授权；
本模块本身不读取数据或启动训练。

## 准备与查看更新

只编码批准模型的权重差，全部数值有限，小端f32/f64；每个完整bundle最多64MiB。
路径、压缩包、pickle和原始数据不是此更新格式。

```python
from suan.federation.updates import encode_arrays, decode_arrays

payload = encode_arrays(parameter_deltas, kind="delta")
info = decode_arrays(payload, expected_kind="delta", expected_layout=approved_parameter_layout)
metadata = {**frozen_update_metadata, "update_sha256": info["sha256"],
            "update_bytes": info["bytes"], "masked": False}
record = registry.prepare_update(grant.grant_id, metadata, payload,
                                model_sha256=locally_verified_base_sha256)
audit = registry.get_update(record.update_id, include_payload=True)
```

其他metadata身份、轮次、样本数和指标来自冻结运行与当前授权。`audit.as_dict()`是分离副本，
`audit.payload`是精确外发字节；默认列表不加载大payload。同grant/round只能保留一个原更新。
首批无SecAgg+，批准的协调方可见单组更新，不提供差分隐私。

## 显式发送与撤回

```python
# 回调由已配对Hub的FederationClient提供，必须核对run/round/recipient并使用有限超时。
sent = registry.send_update(record.update_id, coordinator_id=verified_coordinator,
                            deliver=publish_to_pinned_coordinator)
registry.revoke(grant.grant_id)
```

回调接收分离metadata和不可变payload。先保存sending意图，再重核授权；成功只证明回调交付，
不是聚合或模型登记。撤回阻止后续接受的发送，已接受的有限发送可完成，不能召回已离开字节。
重复send不再次调回调。异常或退出后保留原update身份；显式recover只把sending标为uncertain，
不重发不重训。撤回后仍可查审计；注册表回退或丢失不保证全局恰好一次。

## 协调端聚合

```python
from suan.federation.flower import FlowerAggregator

candidate = FlowerAggregator(explicit_flower_python, timeout=30).aggregate(
    frozen_model_bundle, admitted_update_pairs, participants=approved_participants,
    run_id=run_id, round=round_number, spec_sha256=frozen_spec_sha256)
```

updates是`(metadata,payload)`序列；approved参与方来自可信授权，至少3组。重新检查所有字节、
布局、基础模型、run与轮次，拒绝整批中的坏更新。combined输入最多256MiB；指标键一致，
`num-examples`为权重保留名。返回模型与receipt可独立核对，未登记为活动模型。

## STK 节点与持久协调

本机所有者使用 `NodeFederationService(runtime, private_root, explicit_flower_python,
workspace_root=trusted_runtime_workspace_root)` 登记数值x/y数据并明确approve。
私有根必须与Runtime工作区、共享项目分离；数据摘要绑定完整manifest、列名与实际数据字节。
这是内部线性训练适配，不替合作方决定待讨论的数据格式。各节点共享固定字段/单位/参数布局，
不各自拟合归一化再平均。支持FedAvg/FedProx，不任意导入远端训练代码。

节点部署在已有配对状态上显式选择算法环境：

```bash
suan-node run --state-dir NODE_STATE --federation-python /absolute/algorithm-env/bin/python
```

省略解释器可继续观察旧任务与保护私有身份，但不能新训练；不自动安装环境。owner先在Hub登记
已核对的run、指定paired client与三个以上节点映射；32位设备ID不能当作64位公钥指纹。
Hub可信转发授权不等于私钥持有证明，本机数据同意仍独立生效。
数据/base/delta不进普通Runtime inputs/work，公共work只有净化回执。普通任务/文件/图接口
不能绕过FL私有身份；Runtime本身仍不是同OS用户之间的沙箱。

协调方用已有配对凭据构造 `FederationClient`，再创建 `FederationCoordinator(private_root,
client, FlowerAggregator(explicit_flower_python))`。先 `create(manifest,spec,model_bundle)`，
明确 `prepare_round(run_id)`、`train(run_id,round)`，用 `recover` 只读回查原action，
`observe` 产生新的状态观察，`collect` 才允许节点外发，`aggregate` 只生成未准入候选。
下一轮必须再次明确prepare；重开不训练、不发送、不自动聚合。失败/未知保原身份，
未知发送不重放，聚合中断保留证据供人工核对。取消意图不冒充Runtime终态，run撤销不召回字节。

训练/节点/协议/client/coordinator及真实网络测试位于 `tests/test_federation_*.py`，
Hub ACL/上传/断线测试为 `tests/test_control_federation.py`。
明确设置`STK_FEDERATION_TEST_PYTHON`才启用实际隔离算法验收；缺依赖skip不算通过。
测试清空`STK_TOKEN_PLAN_API_KEY`并取消`STK_TOKEN_PLAN_MODEL`。
