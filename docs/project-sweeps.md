# 参数扫描生成

参数扫描把每个参数的范围或取值列表展开成参数表中的新行，代替逐行添加或手写 CSV。
生成只是一次普通的表格编辑：所有新行在同一修订中写入，可以一次撤销/重做；不会准备运行、
提交任务或调用模型。项目自管的表（已保存分析、文件索引）不能生成扫描。

## 桌面操作

打开项目，在“表格”页选择参数表，展开 **生成参数扫描**：

1. “参数 1”默认选择第一个可扫描字段（数值、整数、文本或是/否）。数值和整数字段可选
   **等间距范围**，填写起点、终点和点数（两端都包含）；也可选 **取值列表**，用英文逗号分隔，
   例如 `300, 350, 400`。文本和是/否字段只用取值列表；文本取值前后空白会去掉，不能包含逗号。
2. **添加参数** 最多四个，每个参数选择不同字段。**组合方式** 为“全部组合”（第一个参数变化最慢）
   或“按顺序配对”（各参数取值个数必须相同）。
3. 选中一行后，**复制所选行的其他单元格** 会把该行未扫描字段的取值、引用和公式复制到每个新行；
   引用本行单元格的公式改为引用新行自身，例如 `T + 10 K` 在新行中读取新行的 `T`。
4. 按钮显示将添加的行数，例如“添加 10 行”。输入不完整、类型不符或超出限制时按钮不可用，
   面板中说明原因。成功后选中第一个新行，结果显示在按钮下方和页面顶部。

点击后先在当前显示的修订上生成计划，再以同一修订写入。生成期间若项目被其他入口修改，
本次不会写入任何行，也不会改到新修订上重试；请检查表格后重新点击。

## Python

桌面 Python 控制台：

```python
p = stk.project
revision = p.snapshot()["project"]["revision"]
plan = p.sweep(TABLE_ID, [
    {"field_id": TEMPERATURE_ID, "start": 300, "stop": 400, "count": 5},
    {"field_id": LABEL_ID, "values": ["bulk", "film"]},
], expected_revision=revision, dry_run=True)
print(plan["rows"])            # 10，未写入
result = p.sweep(TABLE_ID, [...同上...], expected_revision=revision, base_record_id=BASE_ID)
print(result["revision"], result["record_ids"][:2])
```

轴可写成 `{"field_id", "values": [...]}`、`{"field_id", "start", "stop", "count"}` 或
`{"field_id", "start", "stop", "step"}`（终点落在步长上时包含终点）。`mode="zip"` 按顺序配对。
修订不一致时抛出冲突错误，不写入。独立 Python 可直接使用
`suan.project.sweep.plan_sweep(store.snapshot(), ...)` 得到命令，再用 `store.apply(...)` 提交。

## CLI

```sh
suan project sweep ./project --table Cases \
  --range Temperature 300 400 5 --values Label '["bulk","film"]' --dry-run
suan project sweep ./project --table Cases --range Temperature 300 400 5 \
  --base ROW_UUID --expected-revision 3
```

`--table`、`--range`、`--values` 可用名称或 ID；`--dry-run` 只打印计划。写入必须给出
`--expected-revision`，可从 `suan project show` 读取。

## 规则与限制

- 取值必须与字段类型完全一致：整数字段只接受整数，数值字段只接受有限数值；JSON 字段只接受
  Python/CLI 的取值列表，桌面面板不提供。计算出的小数按 12 位有效数字舍入，避免 `0.30000000000000004`。
- 每个参数最多 1000 个取值，最多 8 个参数（桌面面板 4 个），每次最多 1000 行。
- 一次编辑最多 1000 条命令：每个新行 1 条，加上每个扫描字段和每个复制单元格各 1 条。
  例如两个参数且不复制时每行 3 条，一次最多 333 行；超出时请分几次生成。
- 复制所选行只复制已赋值的单元格；未赋值字段在新行中保持未赋值。指向其他行的引用和公式绑定保持原目标。
- 生成不检查物理合理性，也不去重；重复点击会再次添加同样的行，可用撤销恢复。
