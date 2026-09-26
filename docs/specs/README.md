# STK specifications (Milestone 1)

> 中文摘要：本目录是 STK 的英文契约（供外部连接器作者与 LLM 使用）：数据格式、节点图、渲染数据包、监控事件与畴分类，
> 以及对应的 JSON Schema、节点目录与示例。中文使用说明见 [可视化指南](../visualization.md)、[控制服务指南](../hub.md) 与 [runtime 指南](../runtime.md)。

These documents are the published contracts of STK. They were frozen for Milestone 1 (Phase A); later
changes are additive, and a breaking change needs a new major version (`stk.graph/2`, `@2` node
types, and so on). Every machine contract is a JSON Schema (draft 2020-12) under
[`suan/contracts/schemas/`](../../suan/contracts/schemas/), loaded with the standard library by
`suan.contracts.load_schema("<id>")`. Python validation where it matters is hand-written and
NumPy-free (`suan.graph.schema.validate_graph`); `jsonschema` is not a runtime dependency.

## Index

| Spec | Defines | Schemas and machine files |
|---|---|---|
| [stk-data-format-v1.md](stk-data-format-v1.md) | Data model (dataset kinds, fields, units and quantities, geometry, frames, provenance), the VTKHDF + STK profile container, the result manifest `stk.result/1`, the case manifest `stk.case/1`, the connector interface and the muFerro mapping | `dataset-1`, `field-1`, `ref-1`, `result-1`, `case-1`; [`quantities.json`](../../suan/contracts/quantities.json) |
| [stk-graph-v1.md](stk-graph-v1.md) | Node graphs `stk.graph/1`: documents, parameters and `$param`, port types, the node catalog `stk.catalog/1`, validation codes, evaluation and cache keys, the view `stk.view/1`, plots `stk.plot/1`, the result `stk.graph-result/1`, presets, CLI, and the full Milestone-1 node catalog with node semantics | `graph-1`, `node-type-1` (catalog entries and `stk.catalog/1`), `view-1`, `plot-1`; [`catalog/m1_nodes.py`](catalog/m1_nodes.py) → [`catalog/stk-catalog-m1.json`](catalog/stk-catalog-m1.json); [`examples/graph-v1/`](examples/graph-v1/) |
| [stk-render-payload-v2.md](stk-render-payload-v2.md) | Render payload `stk.payload/2`: manifest, content-addressed buffers and accessors, coordinates, colormap LUTs, layer types, profiles and budgets, transport, the `.stkp` single-file form, decoder validation and the scene v1 downgrade | `payload-2`; [`examples/payload-v2/`](examples/payload-v2/) (directory form, `example.stkp`, generator `make_example.py`) |
| [stk-events-v1.md](stk-events-v1.md) | Monitoring events: the JSONL file at `$STK_MONITOR_PATH`, the envelope, event types, the Python emitter and reader, the Runtime endpoint `GET /v1/tasks/{id}/events`, and the muFerro legacy adapter | `event-1` |
| [stk-desktop-bridge-v1.md](stk-desktop-bridge-v1.md) | Desktop bridge protocol v1: NDJSON over the stdio of `python -m suan.desktop_bridge --stdio`, the envelope and error codes, session, connections, hub review, workspaces, resumable transfers, tasks, subscriptions (watch, logs, events), graph evaluation, blobs, probe and colormaps | `desktop-bridge-1` |
| [domain-classifiers.md](domain-classifiers.md) | Clean-room formulas for ferroelectric domains: the cubic-26 direction sets and numberings, orientation classification, film detection, label fractions, orientation and categorical colours, label surfaces | none (implemented by `suan/analysis/` and the analysis/filter nodes of `stk-graph-v1.md`) |

## How they relate

```
native files --connector--> datasets (data format v1) --graph v1 evaluator--> outputs
                                                                               scene -> stk.payload/2 (payload v2) -> web viewer, offscreen PNG, later Blender
                                                                               plot  -> stk.plot/1 -> PNG/SVG + plotted data
                                                                               table, value, dataset descriptor, exported file
analysis nodes (orientation classify, film detect, label fractions, label surfaces) follow domain-classifiers
running program --events v1--> Runtime GET /v1/tasks/{id}/events;  stk.result/1 = fold(events) + files + verification
```

- **Data format v1** is the vocabulary everything else uses: graph `dataset`/`table` ports carry its
  in-memory model, source nodes read native files through its connectors, and units follow its rule
  that units are never guessed (`unspecified`, `1`, `normalized`, `grid_index`, else UCUM).
- **Graph v1** turns datasets into deliverables. Its render nodes produce layers that the **payload
  v2** spec encodes; its plot nodes produce `stk.plot/1`; its analysis nodes follow
  **domain-classifiers**.
- **Events v1** reports a run while it is live. The invariant *stk.result/1 = fold(events) + files +
  verification* ties it back to the result manifest of the data format.

## Consistency checks

- `suan graph schema` prints `graph-1`; `suan graph catalog --json` prints the installed
  `stk.catalog/1`.
- `suan graph doctor` compares the installed built-in node types with
  `catalog/stk-catalog-m1.json` (the `catalog` check).
- `python docs/specs/catalog/m1_nodes.py --write` regenerates `stk-catalog-m1.json`;
  `--update-spec` regenerates the node tables in `stk-graph-v1.md` §13.

Documents that are produced by the implementation but have no JSON Schema yet: `stk.graph-result/1`
(the delivered form is described in `suan/graph/service.py`), `stk.series/1` (`suan graph run
--param NAME=all`), `stk.plot-data/1` (the plotted data next to each plot) and `stk.graph-meta/1`
(the `graph.meta` hub action).
