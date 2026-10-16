# 项目表格导入与导出

状态：2026-10-15，本轮实现 CSV／Excel（`.xlsx`）／版本化 JSON 交换；原生交互与跨平台验收结果由
[验收记录](runtime-validation.md)汇总。本文介绍已实现的接口和限制，不把尚未执行的原生测试当作通过。

普通表格交换用于给外部软件提供数值，或把一个小型数据表导入当前项目。
需要把项目、窗口布局、Viewer 参数和未提交草稿搬到另一台机器时，使用工作空间文件 `.stkworkspace`；
表格文件不保存项目流程、历史、运行记录、文件内容或完整工作空间。
字段类型和视图规则见[多维表格](design/multidimensional-tables.md)，文件与 RPC 契约见[表格交换 v1](specs/table-io-1.md)。

## 桌面操作

独立表格的工具栏直接显示“导入表格”和“导出表格”，无需先进入管理页。传统项目页的 CSV／TSV 面板继续保留。

导入时选择格式，填写或浏览源文件，再点“预览”：

1. CSV 可选逗号或制表符；Excel 默认首张工作表，切换工作表后重新预览。
2. CSV／Excel 默认按文本导入。在列映射中明确选择整数、数值、布尔、JSON、日期、URL 等类型；数值列可填写单位。
   列较多时映射分页。STK 不根据看起来像数字的文字猜测类型。
3. STK JSON 自带类型、单位和选择项配置；预览显示该配置，导入时保持它。JSON 不支持类型／单位覆盖。
4. 填写新表名，明确点击“导入”。导入核对预览的文件 SHA-256 与项目修订，任一错误整体拒绝。
   成功后选中新表，整个导入可一次撤销／重做。导入会生成新的表、字段和记录 ID。

预览不修改项目。更改源路径、格式、工作表或分隔符后，已有预览不能继续用于导入；更改文件字节也需要重新预览。
打开、浏览和切换格式均不执行文件中的程序。

导出时选择 CSV、Excel 或 JSON，指定一个尚不存在的新文件，再明确点击“导出”。输出使用当前视图的可见字段、
全表筛选和排序；当前页的搜索框不影响导出。导出读取一致的项目修订，不修改项目，不覆盖已有目标。
未指定视图的 Python 调用则输出全表存储顺序。

## 格式选择

| 格式 | 适用情形 | 保留与限制 |
| --- | --- | --- |
| CSV／TSV | 与通用工具交换纯文本和数值 | UTF-8；导出带 BOM 和 CRLF。类型、单位和字段配置须在导入时重新声明。 |
| Excel `.xlsx` | 交给 Excel 等软件查看或整理数值 | 真正的 XLSX 文件，输出一张 `Table` 工作表；不保留 STK 字段模式、工作表样式、图表或公式定义。 |
| STK JSON v1 | 保留科研字段类型和缺测语义的值交换 | 保留十种字段、单位、选择项配置、对象值和 unset／null；公式与引用变成求值结果，原项目身份不恢复。 |

JSON 导出中的 `source` 仅记录来源项目、表和修订；它不把文件变成项目备份。
JSON 导入接受 `format: "stk.table"`、`version: 1`、`mode: "evaluated_values"` 的格式，
不接受任意 JSON 对象数组。导出文件可作为可检查的格式样例。

## 数值、缺测与对象

Excel 数字只有 15 位有效数字精度，详见[微软说明](https://support.microsoft.com/en-us/excel/keeping-leading-zeros-and-large-numbers)。
STK 将超过 15 位十进制数字的整数写成文本；再次导入时明确映射为 `integer`，可保留原始 int64。
不能用 15 位有效数字精确往返的浮点数（如 `1.0000000000000002`）、次正规浮点数和负零 `-0.0`
也以完整文字写出；再次导入时映射为 `number`，保留该浮点值和零的符号。普通 `301.25` 等数值仍写成数值单元格。
若数值在外部软件中已被舍入，STK 无法恢复丢失的位数。普通 Excel 数字、布尔和日期在预览中先转为文字，
再按用户声明的列类型转换。

CSV／Excel 中，文本空白保留为字符串，其他类型空白导入为 `null`；它们无法完整保留 unset 与 null 的区别。
JSON 的记录 `values` 中没有某个字段键表示 unset，键存在且值为 `null` 表示显式缺测，两者分别恢复。
整数保留 int64，拒绝超出范围的整数、NaN 和 Infinity。

JSON 的非空 `object` 字段只能导回其来源项目；对象引用继续指向原项目中的既有对象，
不会复制文件、工作流或运行，也不会自动改指向新建的记录。仅 JSON 保存选择项与对象字段所需配置；
当前 CSV／Excel 图形映射提供七种无额外选项的类型，不自动建立单选、多选或对象字段。
旧格式 13 可导入原有五种类型；新类型需要先明确备份升级到 14，导入不会自动升级。

## 公式与 Excel 内容

项目公式或引用导出其成功求值结果，导入后是普通值；有求值错误的目标单元格会阻止导出。
若要保留项目表达式、UUID 和命名视图，应使用项目或工作空间备份。

Excel 导入拒绝所选工作表中的公式和错误单元格；请先在外部软件中明确转换为值。
STK 不读取公式缓存来替代执行结果。宏、外部工作簿链接及任何外部关系均被拒绝。
XLSX 导出的 `=...`、`+...`、`-...` 和 `@...` 字符串明确标为文字。
CSV 中的这些文字在 STK 内也不会执行；外部表格软件如何解释 CSV 取决于该软件的导入方式。

读取器采用 openpyxl 的只读方式，并保留公式标记以便拒绝公式；参数含义可核对
[openpyxl 官方读取器](https://openpyxl.readthedocs.io/en/stable/_modules/openpyxl/reader/excel.html)。
openpyxl 的 [PyPI Security 说明](https://pypi.org/project/openpyxl/#security)建议使用 defusedxml 处理 XML 风险；
STK 在打开工作簿前校验 ZIP 预算，并用 defusedxml 拒绝 DTD、实体和外部引用。

## Python

桌面 Python 的入口是 `stk.project.table_io`，独立 Python 使用 `ProjectStore(directory).table_io`：

```python
p = stk.project
revision = p.snapshot()["project"]["revision"]
preview = p.table_io.preview(
    "/absolute/path/measurements.xlsx", format="xlsx",
    expected_revision=revision,
)
imported = p.table_io.import_file(
    "/absolute/path/measurements.xlsx", format="xlsx", name="Measurements",
    sheet=preview["sheet"], types={"Temperature": "number"},
    units={"Temperature": "K"}, expected_revision=revision,
    expected_sha256=preview["source_sha256"],
)
exported = p.table_io.export_file(
    imported["table_id"], "/absolute/path/new-measurements.json",
    format="json", expected_revision=imported["revision"],
)
```

`expected_revision` 必填；预览 SHA 可以传给 `expected_sha256`。桌面 UI 始终绑定预览 SHA。
独立接口的相对路径以项目目录为基准，桌面 helper 的相对路径以脚本工作目录为基准。
XLSX 需要已安装的 openpyxl 和 defusedxml；缺失依赖时明确报错，不在导入时联网安装。
既有 CSV API 和 CLI 继续兼容，见[CSV 指南](project-csv.md)。

## 当前规模限制

- 输入／输出文件最多 8 MiB，最多 64 列；预览和导出最多 10000 条数据记录。预览显示 1–100 行，桌面请求 20 行。
- 导入仍是最多 1000 条命令的一次原子编辑；命令包括建表、建字段、建记录和设单元格。
  CSV／Excel 有 `C` 列时最多 `floor((999-C)/(C+1))` 行，例如 5 列最多 165 行。
- XLSX／JSON 导入另有 1 MiB 序列化命令预算，预览保守预留表名空间；CSV 保持既有批次规则。
  因此能预览或导出的文件不一定能一次导入。
- XLSX ZIP 最多 2048 个成员、展开合计 32 MiB、最多 256 张工作表；拒绝加密 ZIP 和重复成员。
  XLSX 字符串最多 32767 字符且不得含不允许的 XML 控制字符。旧 `.xls`／`.xlsb` 不受支持。
- JSON 层级最多 64，拒绝重复对象键。CSV 单字段还受 Python CSV 解析器默认长度限制。
- 输出通过同目录临时文件和不覆盖的硬链接发布；目标目录须已存在，文件系统须支持该发布方式。
  导出文件不会因为撤销项目操作而删除，也不会自动加入文件索引。

这套接口提供有界的本地值交换；大表流式导入、多工作表批量导入、Excel 样式／图表往返和公式往返尚未实现。
