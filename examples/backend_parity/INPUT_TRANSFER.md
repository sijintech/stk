# D1 输入传输与现有设备撤权

在同一 Linux 主机启动两套独立 Runtime，以及 B 的真实 Hub 和出站 NodeAgent：

```sh
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
  python -I examples/backend_parity/input_transfer.py --mode source \
  --evidence-dir /tmp/stk-input-evidence
```

安装态使用已安装 `.[server,control,test]` 的解释器和 `--mode installed`，不注入产品源码。
部署、来源摘要、绝对场景预算和清理复用 [正常样例](README.md) 的 `offline.py`。
默认场景预算 170 秒；之后每项清理有独立宽限，总硬截止由外层启动器提供。

两边上传同一份 1048599 字节公开制造输入。先发送 1 MiB，查询进度后重新 begin，
核对原 session 和 offset，再传余下字节并完成 SHA 校验。这是部分会话的续传，
没有注入断网，也没有验证桥传输日志重开。B 的上传设备通过本次 Hub 的显式 desktop 配对创建。

B 的 blob 上传不会直接写入节点工作区：同一 `workspace.import` 必须先处于 review，
此时工作区为空、没有任务；测试操作员读取原请求后批准，才观察原动作成功。
两边用同一公开程序、明确 inputs 和 input_hashes 执行一次，将输入 SHA 写为产物。
B 的完整 TaskSpec 同样经过一次明确批准。核对原 Runtime 的冻结输入清单、精确任务状态、
产物实字节和程序 marker/PID；程序和 worker 均须在最终清扫前退出。

随后仅撤销 B 本次配对的上传设备。核对撤权前原凭据可读，再由 owner DELETE 取得确认；
原 HubClient 的上传 begin/status/chunk/finish、action 读取/原 ID 重放/新建、blob、task/workspace
读取，以及携相同凭据的新 HubClient status，均须收到 HTTP 401。还核对节点仍在线、
没有新增 action、拒绝下载没有目标文件、原 Runtime 任务未变且仍只有一个任务。
这是当前设备权限验证，不定义项目/用户授权；不证明在途请求被中断、已接受动作取消、
已交付缓存被召回或 R3 已实施。A 没有 Hub 设备撤权，这是部署差异。

`assertions.json` 的 I1–I11 分别覆盖续传、完成摘要、工作区文件、人工导入、冻结输入、
程序输出、一次启动、提交批准、撤权拒绝、有效撤权边界和原执行事实保持。
`backend-parity.json` 保存两边的受控阶段值；文件/输入清单仅比较 path、size、sha256。
`requests.jsonl` 只保存工作区、上传完成、导入和提交的摘要，不是完整 HTTP 审计日志。
其余证据与正常样例一致；不导出凭据、原异常文本或个人路径。清理失败或超预算不能通过。

这是单机软件验收；真实许可 MuPRO、跨主机、目标 OS、科学有效性和完整 D1 尚未在本例验证。
