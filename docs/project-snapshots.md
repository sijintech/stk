# 项目输入快照

输入快照保存选定文件在一次显式操作中读到的内容。它与 `project.snapshot` 的当前表格视图不同：
历史清单不会随原文件、文件索引或参数表的修改而改变，适合后续运行使用固定输入。
当前已接入 SQLite、CLI、Python 和原生项目面板；[模拟运行记录](project-runs.md)已关联参数行与输入版本，
[分析执行记录](project-analysis-runs.md)可明确映射快照文件并运行保存的分析。捕获本身不启动这些操作。

## 在界面中使用

1. 打开项目，旧格式先点击“备份并升级项目”。输入快照需要格式 4，打开旧项目不会自动迁移。
2. 在文件表格中选择一个已经存在的文件，展开“输入快照”，点击“保存选中文件的快照”。
   桌面按钮一次复制一个文件，上限 256 MiB；它不改写原文件。
3. “读取历史快照”读取项目保存的清单。选择一个保存修订，可以查看文件名、大小和 SHA-256。
4. “校验快照内容”重新读取历史副本并检查哈希；显示的是这次主动检查的结果，没有后台持续校验。

历史快照独立于表格撤销。撤销登记、删除文件记录，甚至删除原文件，都不会删除已保存的输入副本。
当前没有快照删除或垃圾回收入口，避免误删后续运行可能引用的内容。快照不会自动提交模拟。

## Python 与 CLI

```python
p = stk.project
files = p.files.list()
record_ids = [record["id"] for record in files["records"]]
captured = p.snapshots.capture(record_ids, expected_revision=files["revision"],
                               max_bytes=256 * 1024 * 1024)
snapshot_id = captured["snapshot"]["id"]
print(p.snapshots.list())
print(p.snapshots.verify(snapshot_id))

# 获取一个历史副本：先检查内容，再返回它现在的绝对路径。
frozen = p.snapshots.resolve(snapshot_id, record_ids[0])
print(frozen["path"], frozen["sha256"], frozen["size"])
# 上传时显式保留原文件名；内部对象的文件名是哈希的一部分。
# transfer = stk.runtime("runtime:lab").upload(workspace_id, frozen["path"],
#     remote=frozen["name"], idempotency_key="run-001:input")
# 上传完成后，在提交 spec 中使用 inputs=[frozen["name"]]，
# input_hashes={frozen["name"]: frozen["sha256"]}，让 Runtime 校验实际复制的输入。
```

`capture` 接受 1–100 个已登记文件 ID，重复 ID 合并；允许空文件，拒绝目录、缺失文件和有求值错误的文件记录。
默认预算是全部选中文件合计 256 MiB，可显式设置 `max_bytes`，范围 1 字节至 1 TiB。
文件索引的存在状态不会替代实际检查；捕获时重新解析位置并读取内容。

```bash
suan project snapshots capture /path/to/project FILE_RECORD_UUID --expected-revision 7
suan project snapshots list /path/to/project
suan project snapshots verify /path/to/project SNAPSHOT_UUID
suan project snapshots resolve /path/to/project SNAPSHOT_UUID FILE_RECORD_UUID
```

直接 Python 库对应 `ProjectStore(directory).snapshots`。`get(snapshot_id)` 读取一个完整清单；
`verify` 返回总体 `ok` 及各文件 `ok/missing/invalid` 和原因，不修复或覆盖损坏内容。
`resolve` 对缺失、损坏或不属于该快照的文件报错；原文件是否仍在原位置不影响历史副本解析。
读取/校验不增加项目修订，成功保存快照增加一次修订并发出 `project.changed`。
上传完成后，可将清单中的 SHA-256 放入 TaskSpec 的 `input_hashes`，由支持 `input_checksums` 的 Runtime
检查实际复制到任务目录的内容，见[Runtime 输入检查](runtime.md)。这项检查不会自动上传文件或提交任务。

## 分页读取快照摘要

快照较多时，可先读取有界摘要，再对选中的 UUID 调用 `get`。桥和桌面 Python 均提供
`project.snapshots.list_summaries`；直接 Python 库也使用同名方法。它需要明确的当前项目修订，
默认 `offset=0`、`limit=64`，每页允许 1–64 项：

```python
# 接续上面的捕获示例；期间有其他写入时，先刷新当前项目修订。
page = p.snapshots.list_summaries(expected_revision=captured["revision"], offset=0, limit=64)
print(page["revision"], page["offset"], page["total"])
for summary in page["snapshots"]:
    print(summary["id"], summary["revision"], summary["file_count"])
if page["snapshots"]:
    selected = p.snapshots.get(page["snapshots"][0]["id"])
    print(selected["manifest"]["files"])
```

每项摘要只有 `id`、`kind`、`revision`、`sha256`、`created_at`、`file_count`，不返回文件清单、
路径或资产字节。当前修订、总数和当前页在同一只读事务内读取，按保存顺序分页。
继续读取时令 `offset` 增加本页项数，并保留相同 `expected_revision`；修订变化会返回 `conflict`，
应刷新后从第一页重新选择。当前页有损坏元数据或超过 2 MiB 的清单时，整页报 `invalid_params`，
不会跳过条目或改变分页计数；其他页可独立读取。

摘要的 `sha256` 是已存清单摘要，不代表本次已验证完整清单或副本内容。`get` 读取并校验一个完整
清单的身份和哈希；`verify` 或 `resolve` 才会读取并校验冻结资产字节。这些读取不会增加修订。
原有 `list()` 与 CLI `snapshots list` 仍返回全部完整清单，行为保持不变。桥参数和响应见
[桌面桥契约](specs/stk-desktop-bridge-v1.md)。

## 保存与一致性边界

- 格式 4 新增只追加的 `project_snapshots` 表，保存清单、清单哈希、创建时间和保存修订。
  清单包含项目 ID、来源修订、选中文件记录 ID、原名称/位置、字节数和内容 SHA-256。
  快照 UUID 从项目 ID 与清单哈希派生；清单读取时校验身份与哈希。
- 文件内容放在项目内 `.stk/objects/sha256/前两位/剩余哈希`。相同内容共享对象；
  新的来源修订会产生新的历史清单，即使字节相同，也不改写旧清单。
- 内容先流式写入 `.stk/tmp` 并落盘，再以不覆盖已有对象的方式发布。存储文件系统需要支持同卷硬链接
  （例如常用的 APFS、NTFS、ext4）；不支持时操作报错，不退化成可见的半份对象。
  已有同哈希对象须先校验；发现损坏会报错，不偷偷用原文件覆盖历史。
- 读取期间检查文件身份、大小和修改信息，完成后再次检查全部源文件；检测到变化就拒绝保存清单。
  多文件捕获不是操作系统级的原子目录快照；应在写入输入的程序停止后捕获。
- 复制不持有长时间数据库写锁；最后在事务中重新校验项目修订并一次保存清单/历史。
  失败不会留下半份清单，已发布但未被清单引用的对象可以留在对象库，后续捕获可复用。
  崩溃也可能留下临时文件；当前不自动清理，不能把临时目录当作已完成的快照。
- 快照清单属于执行来源记录，普通表格 `apply/undo/redo` 不会改写或删除它；历史里的 `capture_files`
  不是可撤销的表格编辑。当前参数值、程序版本和整个工作区尚未自动冻结进该文件快照。

移动或复制**完整项目目录**会带上内部副本，原本在项目外的文件也能从快照读取。
仅复制 `project.sqlite3` 或使用“数据库备份”不包含 `.stk/objects`，恢复后清单仍在，但内容校验可能报告缺失。
当前未提供把数据库与全部资源统一打包的一致性备份；复制目录前应关闭项目并停止写入。
