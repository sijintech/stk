# 联邦后端基础：授权、审计与隔离聚合

当前有模型／权重差校验、逐数据集逐run本机授权、更新审计和显式单次发送，
以及独立环境中的Flower聚合。[契约](specs/stk-federation-1.md)规定字段、额度与恢复。
STK出站WSS、Runtime训练、桌面授权界面和完整三节点网络验收仍待完成。
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
# 此回调需由后续已认证STK传输提供，并设置有限超时；本页没有网络适配器。
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

测试入口：`tests/test_federation_updates.py`、`test_federation_consent.py`、`test_federation_flower.py`。
明确设置`STK_FEDERATION_TEST_PYTHON`才启用实际隔离算法验收；缺依赖skip不算通过。
测试清空`STK_TOKEN_PLAN_API_KEY`并取消`STK_TOKEN_PLAN_MODEL`。
