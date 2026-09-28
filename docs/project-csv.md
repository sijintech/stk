# 项目表格 CSV / TSV 交换

CSV 用于准备小型参数表、交换文本和导出计算值。项目本身仍保存在 SQLite 中；CSV 不包含稳定 ID、
公式、引用、单位、输入快照或运行记录，不能作为项目备份。

## 桌面操作

打开项目后展开 **CSV / TSV 表格**：

1. 填写 UTF-8 输入文件的绝对路径和新表格名称。第一行是列名，后续每条 CSV 记录是一行。
2. 默认所有列按文本保存，`001`、`true` 和 `=1+1` 都保持原文本。需要数值等类型时展开“列类型”。
   输入 JSON，例如 `{"Temperature":"number","Enabled":"boolean"}`；数值列单位可填 `{"Temperature":"K"}`。
3. 点击“导入为新表格”。成功后选中该表；任一值错误或项目修订冲突都不会产生部分表格。
   在格式 3 及之后的项目里，整个导入可以一次撤销/重做，恢复保留原 ID。
4. 选中要导出的表，在面板中填写一个**尚不存在**的输出文件绝对路径，点击“导出选中表格”。
   输出 UTF-8 BOM 和 CRLF，包含表头和当前值；已有目标不会被覆盖。导出不改变项目修订。

“使用制表符分隔”同时控制导入和导出。文件后缀不自动决定分隔符。导出文件不会自动加入项目文件索引；
需要时用文件面板登记。关闭/切换项目会清空该面板路径草稿，不执行任何导入导出。

## Python

在桌面 Python 控制台中：

```python
p = stk.project
revision = p.snapshot()["project"]["revision"]
imported = p.csv.import_file(
    "/absolute/path/parameters.csv", name="参数",
    types={"Temperature": "number", "Enabled": "boolean"},
    units={"Temperature": "K"}, expected_revision=revision,
)
print(imported["table_id"], imported["rows"], imported["source_sha256"])

exported = p.csv.export_file(
    imported["table_id"], "/absolute/path/new-output.tsv",
    delimiter="\t", expected_revision=imported["revision"],
)
print(exported["path"], exported["sha256"])
```

独立 Python 使用 `ProjectStore(directory).csv`，方法相同且不依赖桌面/Runtime。
独立接口的相对文件路径基于项目目录；桌面 `stk` helper 的相对文件路径基于脚本当前工作目录。
导入返回新修订、表/字段/记录 ID、行列数和所读源文件的 SHA-256；不自动保存源文件副本。
导出返回所读取的修订、表 ID、路径、行列数、字节数和内容 SHA-256。
若导出期间其他入口继续编辑，输出仍对应返回的那次一致读取，不混合多个修订。

## CLI

```sh
suan project csv import ./project ./parameters.csv --name Parameters \
  --types '{"Temperature":"number","Enabled":"boolean"}' \
  --units '{"Temperature":"K"}' --expected-revision 0
suan project csv export ./project TABLE_UUID ./new-output.csv --expected-revision 1
```

CLI 路径基于当前工作目录，`--tsv` 选择制表符。JSON 参数在 Windows PowerShell 中按对应 shell 的
引号规则传递；也可在桌面面板填写相同 JSON。实际修订号需从 `suan project show` 读取。

## 格式与首版限制

- 支持 UTF-8 和可选 BOM；CSV 引号中的逗号、制表符、引号与换行按标准 CSV 解析。
  列名必须非空且唯一，最多 64 列；每条记录的值数须与表头完全一致，空白行不会自动忽略。
- 类型只有 `text`、`integer`、`number`、`boolean`、`json`。非文本列使用 JSON 字面量，
  例如整数 `12`、数值 `1e-3`、布尔 `true`/`false`；拒绝 `NaN`/`Infinity` 和超出 int64 的整数。
  非文本空白单元格导入为 `null`；文本空白保留原字符串。JSON 单元格按普通 CSV 规则引用。
- 输入和输出均不超过 8 MiB；单字段长度也受 Python CSV 解析器限制（默认 131072 字符）。
  导入复用最多 1000 条命令的原子修改批次：有 `C` 列时最多
  `floor((999 - C) / (C + 1))` 条记录，例如 5 列最多 165 条，10 列最多 89 条。
  超限整体拒绝；大规模数据导入和流式表格编辑仍待后续实现。导出最多 10000 条记录。
- 导出使用当前表的字段/记录存储顺序，不使用界面的临时排序。公式输出当前计算值，
  有求值错误的单元格会阻止导出；未赋值和普通 `null` 导出为空白，JSON 列导出 `null`。
  文本 `null` 与空文本无法通过 CSV 区分；重新导入会产生新对象 ID。
- 文件中的文本不会被 STK 解释为公式；CSV 不携带项目类型声明，重新导入时需再次指定类型/单位。
- 导出先写同目录临时文件，再以不覆盖的硬链接方式发布；当前要求目标文件系统支持硬链接。
  写入失败会清理临时文件，成功导出的文件不会随项目撤销而删除。
