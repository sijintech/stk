# 项目运行记录

格式 5 将参数表中的一行、输入快照、完整 TaskSpec、连接目标、固定幂等键和远端任务关联起来。
Python 控制台已提供 `stk.project.runs`；原生项目表格的“运行记录”面板可查看方案、提交、刷新和取消。
准备方案只写项目数据库，明确提交才调用 Runtime。
本阶段不自动生成求解器输入，也没有 AI 计划生成器。每行的参数怎样转换为命令或输入文件，由脚本明确给出。

可直接测试的[温度扫描示例](../examples/project_scan/README.md)串联参数表、输入快照、远端执行、
VTK/PNG 下载和稳定 ID 的结果比较表；演示使用合成场，非真实物理求解。

## 原生面板

在“项目表格”展开“运行记录”，点击“加载运行记录”，每页最多 100 条。选中一行后显示连接、参数新旧
状态、命令和已接受的任务；“冻结参数与输入”可展开只读参数表、工作区和输入哈希。点击“选择来源参数行”
回到编辑表格。加载列表/详情不会访问远端，也不会提交任务。

“提交运行”执行选定方案；响应不确定时显示“恢复提交”，继续使用原幂等键。旧参数方案需明确勾选允许
运行旧参数，后端也再次检查。已取得任务 ID 的记录禁止再次提交；使用“刷新状态”读取远端，“取消任务”
取消尚未结束的任务。Hub 待审核状态继续在 Jobs 处理。此面板尚不提供输入生成器或批量准备向导。

项目编辑和 Python 操作的通知会刷新已加载的运行列表；外部 CLI 修改仍需先刷新项目。关闭/切换项目
清空面板缓存，重新打开后从数据库读取历史；桥重启不会重放提交。运行状态更新不推进参数修订。

## 准备、检查和执行

先用已有 `stk.runtime()` 创建工作区，并将[输入快照](project-snapshots.md)的副本上传到明确的相对路径。
随后准备方案；下面的 `table_id`、`row_id`、`workspace_id`、`snapshot_id`、`file_record_id` 都是已有对象的 ID：

```python
p = stk.project
prepared = p.runs.prepare([
    {
        "table_id": table_id,
        "record_id": row_id,
        "label": "300 K",
        "input_snapshot_id": snapshot_id,
        "input_bindings": {"input.json": file_record_id},
        "spec": {
            "workspace_id": workspace_id,
            "argv": ["solver", "input.json"],
            "outputs": ["result.vtk"],
        },
    },
], connection="runtime:cluster", expected_revision=p.snapshot()["project"]["revision"])
run_id = prepared["run_ids"][0]
plan = p.runs.get(run_id)  # 查看冻结参数、输入 SHA-256 和命令，不执行
```

`prepare` 一次接受 1–100 个明确条目，整个批次只增加一个项目修订。任意一行缺失、含公式错误、输入绑定
无效或修订过期，整个批次均不保存。单方案上限 256 KiB，批次合计 4 MiB。
Hub 连接需同时提供 `node`。准备只读取保存的连接配置，不做远端健康检查或创建工作区；本机 `local`
连接仍要求已经启动的本机 Runtime 以确定地址。连接凭据不复制进方案。

不传 `input_bindings` 时，以快照中的文件名作为远端相对路径；同名文件必须显式指定不同路径。
不传输入快照时，执行规格会固定 `inputs=[]`，不会隐式复制整个工作区。
系统根据快照写入 `inputs` 和 `input_hashes`；Runtime 校验实际复制到任务目录的字节后才排队，
远端缺少文件或内容变化会失败，不会用新内容运行旧方案。需要支持 `input_checksums` 的 Runtime。

明确执行与观察：

```python
run = p.runs.submit(run_id)
run = p.runs.refresh(run_id)  # 只读远端状态，不提交、不自动重试
# 必要时明确取消已取得任务 ID 的运行：
# run = p.runs.cancel(run_id)
```

`submit` 先保存执行意图，再发送固定请求。响应丢失时，重新打开同一项目，再明确调用
`submit(run_id)` 恢复同一个幂等请求；不会分配新键。已保存任务 ID 后再次提交只返回记录，
状态更新使用 `refresh`。`refresh` 不会把 prepared/uncertain 记录变成新的提交。
查看 `run["status"]["task"]` 获取已有任务 ID、状态、输入清单和规格；日志、产物和下载仍通过
`stk.runtime(...).tasks` 与 `download`，不自动下载结果。

失败尝试保留原键和任务事实；若要修改配置或重新运行，明确准备一个新方案。不要更改数据库中的旧方案。
Hub 待审核操作保留 `action` 与 `review` 状态；审核继续在已有 Jobs 流程完成，脚本不自动批准。
`refresh` 可读取已审核完成的提交/取消操作。尚未取得任务 ID 的待审核提交须在 Jobs 中处理，不能当成
已接受的任务取消。关闭项目、退出控制台或中断 Python 等待不会取消远端任务。

## 参数变化、连接身份和历史

每个方案冻结表格/记录/字段 ID、当时的有效值、定义和单位，附源修订号及规范 JSON 的 SHA-256。
`parameter_state` 为 `current`、`changed`、`missing` 或 `error`。表格/字段改名不改变有效参数身份；
公式的上游值变化、定义变化、字段增删会标记旧方案。撤销参数修改可以恢复为 current，旧方案始终保留。
这是行级有效参数比较，不是完整程序环境或全部依赖链快照。

尚未提交的过期方案默认拒绝执行；通常应重新准备。明确希望运行已冻结的旧参数时可用
`submit(run_id, allow_stale=True)`。已有持久执行意图的显式重试继续恢复原请求，不因当前参数变化而创建新任务。
方案本身不重新生成 argv 或输入文件。

保存连接 URL/SSH Host（Hub 同时包含 node）的无凭据指纹。配置名称相同但目标地址改变时，拒绝提交、
刷新和取消旧运行；恢复原配置后才可操作。它防止配置误指向，不是远端机器的加密身份认证。
凭据轮换不改变此指纹；不要将不同服务实例复用相同地址视为已验证的同一台机器。

运行方案是只追加的历史事实；远端观察记录不增加可编辑项目修订，也不进入表格撤销栈。
数据库备份包含这两类记录；输入对象仍在 `.stk/objects`，完整备份需一起保存项目文件夹。
外部可执行程序、Python 环境、系统库和队列环境不会自动冻结；将程序文件纳入输入快照可保存其实际字节。

```python
page = p.runs.list(limit=100)
while page["next_offset"] is not None:
    page = p.runs.list(offset=page["next_offset"], limit=100)
```

列表只返回紧凑摘要；完整方案用 `get` 获取。列表与详情中的参数新旧状态来自当次读取，不保证后续编辑后仍相同。
目前不提供删除运行历史、自动重试、批量后台派发或项目打包。
