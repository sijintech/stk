# STK graph v1 (`stk.graph/1`): documents, node catalog, validation and evaluation

> 中文摘要：本文档定义 STK 节点图 `stk.graph/1`：带类型端口、带命名空间与版本的节点类型、参数的 `x-stk-stage`
> （data 参数改动会重算下游，client 参数只改外观、不回服务器）、图参数与 `$param` 引用、校验错误码、缓存键（Merkle 哈希）
> 与求值器接口，以及里程碑 1 的完整节点目录（每个节点的类型 ID、端口、参数、默认值、范围与阶段）。

Status: frozen for Milestone 1 (Phase A). Machine contracts: `suan/contracts/schemas/{graph-1,
node-type-1,view-1,plot-1}.schema.json`; the M1 catalog as JSON: `docs/specs/catalog/stk-catalog-m1.json`
(generated from the declarations in `docs/specs/catalog/m1_nodes.py`). Python:
`suan/graph/registry.py` (registration API, port lattice, evaluator interfaces) and
`suan/graph/schema.py` (NumPy-free validation, canonical JSON, graph hash). Example graph:
`docs/specs/examples/graph-v1/muferro-domains.json`.

## 1. Model

A graph is a JSON DAG of typed, versioned nodes. It goes to the data: a headless evaluator runs next
to the files (node agent, CLI or desktop), caches every node result by a Merkle content hash, and
sends back small results (render payloads, PNGs, tables, plots). Two pipelines share the same
references and caches: the 3D pipeline (sources → filters/analysis → render → view → outputs) and the
statistics pipeline (tables → plots).

Node **stages** follow the node family (the middle segment of the type id):

| family | stage | runs | cached by |
|---|---|---|---|
| `source` | `source` | evaluator (reads files through a binding) | data key (includes file content) |
| `filter` | `data` | evaluator | data key |
| `analysis` | `analysis` | evaluator | data key |
| `render` | `representation` | geometry in the evaluator; appearance attached by `finalize` | data key (geometry), full key (appearance) |
| `view` | `view` | evaluator (cheap) | full key |
| `output` | `output` | evaluator (payload encode, offscreen render, export) | full key |
| `plot` | `plot` | evaluator (spec + matplotlib) | full key |

Every parameter declares `x-stk-stage`: `data` (changing it re-runs this node and everything
downstream) or `client` (appearance only: colormap, opacity, glyph shape/scale factor, legend
position, camera, viewport; it never re-runs a data-stage node). Source/data/analysis nodes have only
data-stage params. For view/output/plot nodes the annotation is informational (they are keyed by the
full key anyway); by default their params are `client`.

## 2. Graph document

```json
{"schema": "stk.graph/1", "id": "…", "name": "…", "description": "…", "catalog": {"stk": 1},
 "parameters": [{"name": "step", "type": "step", "default": "latest"}],
 "time": {"domain": "step", "current": 1000, "range": [0, 10000], "stride": 100,
          "policy": "latest_at_or_before", "fps": 12},
 "nodes": [
   {"id": "run", "type": "stk.source.muferro_run@1", "params": {"binding": "run"}},
   {"id": "polar", "type": "stk.source.muferro_frame@1", "inputs": {"frames": {"from": "run.frames"}},
    "params": {"dataset": "Polar", "step": {"$param": "step"}}},
   {"id": "scene", "type": "stk.view.scene@1",
    "inputs": {"layers": [{"from": "surface.layer"}, {"from": "box.layer"}], "camera": {"from": "cam.camera"}}}
 ],
 "outputs": {"scene": "scene.scene", "fractions": "fractions.out"},
 "ui": {"positions": {"run": [0, 0]}}}
```

| key | required | rules |
|---|---|---|
| `schema` | yes | `"stk.graph/1"` |
| `id`, `name`, `description`, `ui` | no | never affect evaluation or cache keys |
| `catalog` | no | minimum catalog version per namespace, e.g. `{"stk": 1}`; `null` = any |
| `parameters` | no | ≤ 64 graph parameters (§2.2) |
| `time` | no | animation context (§6) |
| `nodes` | yes | 1–200 nodes |
| `outputs` | yes | ≥ 1 entries `name → "node.port"`; the port type must be deliverable (§3.4) |
| `extensions`, `x-*` | no | free; ignored by evaluation |

Limits: 200 nodes; 256 KiB of canonical JSON per graph; 64 KiB of params per node (larger data
must be a dataset reference).

### 2.1 Nodes and links

- `id` matches `^[a-z][a-z0-9_]{0,63}$` and is unique. `type` is `namespace.family.name@major`
  (e.g. `stk.filter.contour@1`); unknown types are kept unchanged (round-trip safe) and reported as
  `unknown_type` (not evaluable).
- `params` maps declared param names to JSON values (or `$param` references). Omitted params take
  their declared defaults; params without a default are required.
- `inputs` maps input port names to a link `{"from": "<node>.<port>"}` (optionally `"as": "<alias>"`),
  or, for `multi` ports only, a list of links (order is significant: e.g. layer order).
- `label`, `description`, `ui` and `x-*` keys never affect evaluation or cache keys.
- Graphs never contain filesystem paths: sources take a `binding` name (resolved by the caller to
  `{task_id}` or a local directory) plus a relative `path` inside it (no leading `/`, no drive letter,
  no `..`, no backslash).

### 2.2 Graph parameters and `$param`

`parameters: [{"name", "type", "default", "choices"?, "minimum"?, "maximum"?, "unit"?, "label"?,
"description"?, "ui"?}]` with `type` one of:

| type | values |
|---|---|
| `number` / `integer` | finite number / integer (with optional `minimum`/`maximum`) |
| `boolean`, `string` | |
| `step` | integer ≥ 0, `"latest"` or `"first"` |
| `vector3` / `int3` | 3 numbers / 3 integers |
| `range` | `[lo|null, hi|null]` |
| `enum` | one of `choices` (required) |
| `json` | any JSON |

A node param value, or any value nested inside it, may be `{"$param": "<name>"}` (an object with
exactly that key). The evaluator substitutes the effective value (caller override, else default);
validation does the same and checks the result against the node param's schema (`param_ref_type` on
mismatch). A parameter whose own declaration is invalid is reported once (`invalid_parameter`), not
at every reference. Other `$`-prefixed keys are reserved (`$anim` is
defined for a later version; M1 rejects it with `reserved_key`).

## 3. Types

### 3.1 Port types (lattice; `suan.graph.registry.PORT_TYPES`)

| type | parent | value inside the evaluator |
|---|---|---|
| `any` | — | anything (utility ports only) |
| `dataset` | any | `suan.data.model.Dataset`; qualified by kind (`accepts` on inputs, `kind`/`kind_from` on outputs); never leaves the evaluator |
| `table` | dataset | `suan.data.model.Table` (kind `table` or a refinement) |
| `value` | any | small JSON value; `value_type` json, number, integer (⊂ number), boolean, string, vector3, range |
| `field` | any | `{name, component}` |
| `colormap`, `palette`, `transfer_function` | any | lookup-table specs (client stage) |
| `layer` | any | render layer (geometry + appearance), defined by `suan/render` (B3) |
| `camera` | any | camera object of stk.view/1 |
| `scene` | any | ordered layers + view (B3); delivered as a payload |
| `plot` | any | stk.plot/1 spec with bound tables (B3) |
| `image` | any | rendered raster: `{media_type, sha256, width, height, bytes}` — unrelated to the dataset kind `image` |
| `payload` | any | encoded stk.payload/2 (manifest + buffers) |
| `file` | any | exported file `{name, media_type, sha256, size, path?}` |

Dataset kinds (`DATASET_KINDS`): `image` ⊃ `labels`; `polydata` ⊃ `points`; `table` ⊃ `frames`;
plus `rectilinear`, `structured`, `unstructured`, `particles`, `collection` (specified, not
implemented in M1). An output whose kind is always a table uses port type `table`.

### 3.2 Compatibility (`ports_compatible`)

An output can feed an input iff

1. the output's port type is a subtype of one of the input's types (inputs may list a union, e.g.
   `["scene", "plot"]`), and
2. for dataset/table ports: at least one possible output kind (a single kind, a list of possible
   kinds, or the kind of whatever is linked to the `kind_from` input) is a subkind of an accepted
   kind (`accepts` absent = any), and
3. for value ports with both `value_type`s set: output value type ⊂ input value type.

This static check means "may be compatible". The evaluator re-checks the actual dataset
(`Dataset.kinds()`) at run time and fails the node with `kind_mismatch` otherwise.

### 3.3 Client types

`CLIENT_TYPES = {layer, camera, scene, plot, image, payload, colormap, palette, transfer_function}`:
values of these types depend on client-stage params. A representation node that consumes one
(e.g. a scalar bar reading a layer) is cached by its full key.

### 3.4 Deliverable output types

Graph outputs may name ports of type `dataset` (delivered as its descriptor), `table`, `value`,
`scene` (delivered as a payload), `plot`, `image`, `payload`, `file`. Other types → `bad_output`.

## 4. Node types and the catalog

### 4.1 Catalog entry (`node-type-1`)

```json
{"id": "stk.filter.contour@1", "type": "stk.filter.contour", "version": 1, "impl_version": 1,
 "stage": "data", "category": "filter", "title": {"en": "Contour", "zh": "等值面"},
 "description": {"en": "…"},
 "inputs": [{"name": "in", "type": "dataset", "accepts": ["image"], "required": true, "multi": false}],
 "outputs": [{"name": "out", "type": "dataset", "kind": "polydata"}],
 "params": {"type": "object", "additionalProperties": false, "required": ["field"],
            "properties": {"field": {"anyOf": ["…"], "x-stk-widget": "field", "x-stk-field-of": "in",
                                     "x-stk-stage": "data"},
                           "values": {"anyOf": ["…"], "default": null, "x-stk-stage": "data"}}},
 "time_dependent": false, "deterministic": true, "cache": "disk"}
```

- `version` is the major version in the type id; a breaking change of ports or params needs a new
  major (`@2`), and both may be installed. `impl_version` changes whenever results change for the
  same params (it is part of the cache key).
- `time_dependent`: results may change while a run is live (sources); `deterministic: false` nodes
  are never disk-cached (random sampling takes an explicit `seed` instead).
- `cache`: `memory` (default), `disk` (only for dataset/table/value outputs) or `none`.
- `stretch: true` marks specified node types that an installation may lack.
- The exported catalog (`Registry.catalog()`, `suan graph catalog --json`) is `stk.catalog/1`:
  `{"schema", "generated_by", "namespaces": {"stk": 1}, "port_types", "kinds", "value_types",
  "client_types", "nodes": [...]}` (validates against `node-type-1#/$defs/catalog`).
  `Registry.from_catalog(doc)` rebuilds a declaration-only registry that validates graphs exactly
  like the Python one (the hub, web and LLM tools can validate without importing node modules).

### 4.2 Parameter schemas

Each param is a JSON Schema fragment using this subset (implemented by
`suan.graph.schema.check_value`): `type` (incl. lists such as `["number", "null"]`), `enum`, `const`,
`minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `minLength`, `maxLength`, `pattern`
(Python `re.search`), `items`, `prefixItems`, `minItems`, `maxItems`, `uniqueItems`, `properties`,
`required`, `additionalProperties`, `propertyNames`, `minProperties`, `maxProperties`, `anyOf`,
`oneOf`, `allOf`, `not`, `if`/`then`/`else`. JSON semantics: booleans are not numbers; `1.0` is an
integer; NaN/Infinity are rejected. Annotations: `title`, `description`, `default`,
`x-stk-stage` (required), `x-stk-widget` (`field`, `field_list`, `step`, `binding`, `path`, `color`,
`colormap`, `palette`, `vector3`, `int3`, `range`, `transfer_function`, `camera`, `json`),
`x-stk-field-of` (input port whose fields populate a field picker), `x-stk-unit`, `x-stk-quantity`,
`x-stk-group`, `x-stk-advanced`, `x-stk-choices-from: "evaluator"` (choices reported at run time),
`x-stk-title-zh`.

Common shapes:

- **field reference**: `"Polar"` or `{"name": "Polar", "component": 0 | "magnitude" | null}`;
  normalized to the object form. `component: null` on a multi-component field means the magnitude
  for scalar uses (threshold, contour, volume, heatmap, histogram).
- **step**: integer ≥ 0, `"latest"` or `"first"`.
- **colour spec** (render nodes, client stage): `{"by": "solid" | "field" | "orientation", "solid":
  [r,g,b(,a)], "field": name, "component": int | "magnitude" | null, "colormap": name, "palette":
  id, "range": [lo|null, hi|null], "range_mode": "data" | "symmetric" | "fixed" | "global",
  "lightness_range": [l0, l1]}`. A label field is coloured with its categories/palette (nearest
  sampling). `orientation` uses `stk:orientation-hsl` (`domain-classifiers.md` §6.2) with the
  maximum magnitude of the layer. `global` combines per-frame stats when available (M1 may treat it
  as `data`).

### 4.3 Registration API (Python)

```python
from suan.graph.registry import Port, node, field_ref, number_list, boolean

@node("stk.filter.contour", version=1, impl_version=1, title={"en": "Contour", "zh": "等值面"},
      inputs=[Port("in", "dataset", accepts=["image"])],
      outputs=[Port("out", "dataset", kind="polydata")],
      params={"field": field_ref(of="in"),
              "values": number_list(None, nullable=True, min_items=1, max_items=32),
              "compute_normals": boolean(True)},
      cache="disk")
def contour(ctx, inputs, params):
    image = inputs["in"]                     # suan.data.model.ImageData
    ...
    return {"out": polydata}                 # or just `polydata` for a single output
```

- `node(type, *, version=1, impl_version=1, title, description=None, inputs=(), outputs, params=None,
  stage=None, time_dependent=False, deterministic=True, cache="memory", finalize=None,
  fingerprint=None, meta=None, tags=(), stretch=False, selectors=(), registry=None)` attaches
  `fn.stk_node_type` (a `NodeType`); `Registry.node(...)` also registers it. `selectors` (source
  nodes with a `fingerprint` only) names the data params that merely select which content is read
  (e.g. `("step", "policy")`); they are left out of the data key (§5). It is an evaluation detail of
  the Python registration and is not exported in the catalog.
- `Port(name, type, *, accepts=None, kind=None, kind_from=None, value_type=None, required=True,
  multi=False, title=None, description=None)`.
- Param helpers (all accept `default` first, then keyword `nullable`, `stage` (`"data"`/`"client"`),
  `title` (str or `{en, zh}`), `description`, `widget`, `field_of`, `unit`, `quantity`, `group`,
  `advanced`): `number(minimum, maximum, exclusive_minimum, exclusive_maximum)`,
  `integer(minimum, maximum)`, `boolean`, `string(pattern, min_length, max_length)`,
  `enum(choices, default)`, `vector3`, `int3(minimum, maximum)`, `color(alpha=False)`, `interval`,
  `array(items_schema, min_items, max_items, unique)`, `number_list`, `string_list`,
  `field_ref(of="in", component=True)`, `step("latest")`, `binding()`, `rel_path()`,
  `json_param(schema, default)`. `REQUIRED` (the default of `default`) marks a required param.
- `Registry(nodes=(), *, namespaces=None)`: `register(obj, *, replace=False)` accepts a `NodeType`,
  a decorated function, a module (collects its decorated functions), a list, or a callable returning
  any of these — the forms an `stk.nodes` entry point may take; `get(id)`, `types()`, iteration,
  `catalog(include_impl=False)`, `Registry.from_catalog(doc)`. Duplicate ids raise unless
  `replace=True` (higher-priority private packages).
- Registration checks: ids and names; known port types and kinds; kinds only on dataset/table
  ports; `kind_from` names a dataset input; defaults satisfy their schemas; no client params on
  source/data/analysis nodes; disk cache only for deterministic dataset/table/value outputs; source
  nodes with an `impl` need a `fingerprint` unless `cache="none"`; `selectors` are data params of a
  source node.

### 4.4 Implementation contract

- `impl(ctx, inputs, params)`: `inputs` maps linked input ports to values (multi ports → list in
  link order; unlinked optional ports are absent); `params` are **normalized**
  (`NodeType.normalize_params`: defaults filled, `$param` substituted, integral floats → int for
  integer schemas, numbers → float, field references → objects). Returns `{port: value}` (a bare
  value if exactly one output).
- Representation nodes: `impl` receives **only data-stage params**; the evaluator then calls
  `finalize(ctx, outputs, client_params) -> outputs`. The default `attach_appearance` merges
  `{"appearance": {...client params}}` into dict layers or calls `value.with_appearance(dict)`.
- `fingerprint(ctx, inputs, params) -> JSON`: describes the content a node reads (e.g.
  `[{"path", "sha256", "reader", "selector"}]`); it becomes `source` in the data key. A source
  node's keys do not include its selector params or the keys of its inputs (§5), so the fingerprint
  must describe everything the node reads, including what it takes from its inputs (for
  `stk.source.muferro_frame`: the chosen row's path, sha256, reader and components). Two steps
  that resolve to the same frame file share one cache entry. Choices reported by a fingerprint
  (`ctx.report_choices`) are fresh for every evaluation.
- `meta(ctx, input_metas, params) -> {port: meta}` (optional): cheap metadata pass (kinds, fields,
  ranges, frames) for UIs (`graph.meta`).
- Nodes must not import NumPy/VTK at module import time (the hub imports catalogs without them).
- Errors: raise `suan.graph.registry.NodeExecutionError(message, code=...)` with a stable code; the
  evaluator attaches the node id.

### 4.5 NodeContext (provided by the evaluator)

```python
class NodeContext(Protocol):
    node_id: str; node_type: NodeType; budget: Budget; cancel: CancelToken
    parameters: Mapping[str, Any]          # effective graph parameters
    cache_dir: Path | None                 # scratch space for large intermediates
    data_key: str                          # this node's data key (hex)
    def resolve(self, binding: str) -> FileSource: ...
    def check(self) -> None: ...           # raises Cancelled / BudgetExceeded; call between chunks
    def progress(self, fraction: float | None = None, message: str = "") -> None: ...
    def warn(self, message: str, *, code: str = "node_warning", **details) -> None: ...
    def report_choices(self, param: str, choices: Sequence, *, value=None) -> None: ...
    def cached(self, name: str, compute: Callable[[], T], *, disk: bool = False) -> T: ...
```

`Budget(max_seconds=300.0, max_memory_mb=None, max_output_bytes=None, profile="web")`;
`CancelToken().cancel(reason)`, `.cancelled`, `.raise_if_cancelled()`; exceptions `GraphError(code,
message, node=None, path="", hint=None)`, `GraphValidationError(issues)`, `Cancelled`,
`BudgetExceeded`, `NodeExecutionError`.

## 5. Evaluation (implemented by `suan.graph.evaluator.evaluate`, Phase B2)

```python
def evaluate(graph, *, registry, resolver, outputs=None, parameters=None, cache=None, budget=None,
             cancel=None, on_event=None) -> EvaluationResult
```

1. Validate (`check_graph` → `GraphValidationError`).
2. Resolve effective parameters; select the ancestors of the requested outputs
   (`topological_order(graph, outputs)`, document order among ties).
3. For each node in order: check cancel/budget; substitute `$param`; normalize params; compute keys;
   reuse a cache hit or run `impl` (then `finalize` for representation nodes); emit `on_event`
   (`node.started`, `node.cached`, `node.finished`, `progress`, `warning`).
4. Return `EvaluationResult(graph_hash, outputs, output_types, parameters, keys, evaluated, timings,
   cache, warnings)`.

**Cache keys** (hex sha256 of canonical JSON, `suan.graph.schema.canonical_json`: sorted keys, no
whitespace, UTF-8, shortest round-trip floats, −0.0 → 0.0, no NaN):

```
data_key(N) = sha256(canonical({"type": id, "impl": impl_version, "params": data-stage params (normalized),
                                "inputs": {port: [data_key(upstream) + ":" + upstream_port, ...]},
                                "source": fingerprint or null}))
full_key(N) = sha256(canonical({"data": data_key(N), "client": client-stage params (normalized),
                                "inputs": {port: [full_key(upstream) + ":" + upstream_port, ...]}}))
```

**Content-keyed source nodes.** A source node (stage `source`) with a `fingerprint` is keyed by
the content it resolved, not by how it was selected:

```
data_key(S) = sha256(canonical({"type": id, "impl": impl_version,
                                "params": data-stage params without the node's selectors,
                                "inputs": {}, "source": fingerprint(resolved content)}))
full_key(S) = sha256(canonical({"data": data_key(S), "client": {}, "inputs": {}}))
```

**Node ids in keys.** Keys are content-only, so graphs that name their nodes differently share the
cache entries of their source, filter and analysis nodes. Representation, view and output nodes put
node ids into their values (layer `id`/`node` and `pick.probe.node`, the scene title overlay, the
`scene_v1` dataset id, export file names), so their `data_key` also holds
`"ids": {"node": <own id>}`, and for representation nodes `"upstream": [the sorted ids of every
ancestor]`. A layer is therefore never reused under another graph's ids, and `pick.probe.node` (the
source node recorded in the dataset's provenance) is always a node upstream of the layer in the graph
being evaluated, else the layer's own node (`ctx.ancestors` lists them). Nodes of other stages keep
the key above (no `ids` member).

The selectors (`stk.source.muferro_frame@1`: `step`, `policy`) and the upstream keys (the frame
listing of `stk.source.muferro_run@1`, whose key changes whenever a live run appends an energy row
or a progress line) are excluded once the fingerprint has resolved the frame; the fingerprint
(path, sha256, reader, components of the chosen frame) stands for both. Consequences: `step: 3`
(resolving to frame 2 under `latest_at_or_before`), `step: 2` and a `latest` that resolves to frame
2 share one entry; appending energy rows to a live run re-runs the run index and what reads the
energy trace, never the frame reader or the nodes derived from an unchanged frame. Every other node
keeps the Merkle keys above (its keys include its upstream keys).

Choices and warnings are stored with a cache entry and replayed on hits, but choices reported
during the current evaluation (a fingerprint resolving the step on a live run) win over replayed
ones, so the step scrubber always lists the frames that exist now.

**Request profile.** A node param named `profile` whose value is `"auto"` is replaced by the
evaluation's `Budget.profile` (the request profile) before keys are computed, so the key names the
effective profile. `stk.output.payload@1` defaults to `profile: "auto"`; an explicit profile wins.

- Source/data/analysis nodes: value cached by `data_key` (then `full_key` adds nothing).
- Representation nodes: `impl` result cached by `data_key` (or `full_key` if an input has a client
  type); `finalize` output keyed by `full_key` (memory only).
- View/output/plot nodes: cached by `full_key`.
- Consequences (tested in Phase B2 and `tests/test_graph_live.py`): a camera or colormap change
  re-runs only view/output nodes (on a live run also the run index and energy-derived nodes); a step
  change re-runs from the frame reader onward unless it resolves to a frame already read; revisiting
  a step hits the cache.
- Tiers: an in-memory LRU (bytes-bounded) and a disk store `<cache>/objects/aa/<key>` for nodes with
  `cache="disk"`; `ctx.cached(name, ...)` sub-keys by `(data_key, name)`.
- `graph_hash(graph)` = `"sha256:" + sha256(canonical(graph without id/name/description/ui/x-*,
  node label/description/ui/x-*, parameter label/description/ui; nodes and parameters sorted))`.

Security: a graph is data; node types are code installed by the operator. No `eval` (the M1
calculator has fixed operations only). Sources read only through bindings. Budgets are enforced
between nodes (and by `ctx.check()` inside long nodes). Runtime error codes (the `code` of a node error
in `errors`, or of the failed request): `bad_request` (a malformed request), `unknown_preset`,
`cancelled`, `budget_exceeded`, `node_failed` (an unexpected exception), `bad_outputs` (a value that
cannot be delivered), `kind_mismatch`, `invalid_param`, `invalid_input` (an input a node cannot use,
e.g. a frames table without its binding), `invalid_data` (unreadable or inconsistent file content),
`invalid_payload`, `invalid_direction` and `numbering_unsupported` (classifier inputs), `not_planar`,
`unknown_binding`, `frame_not_found`, `missing_file`, `path_not_allowed` (a path leaving its binding),
`invalid_path`, `connector_error` (a connector failure without a more specific code),
`render_unavailable` (no offscreen OpenGL; the hint says how to get it), `render_failed` (the render
child failed) and `unsupported`; an invalid graph fails with the validation codes of §11.

## 6. Time and animation

- The step is a graph parameter (type `step`) bound to source params (`"step": {"$param": "step"}`).
  `stk.source.muferro_frame@1` resolves `latest`/`first`/an integer with `policy` and calls
  `ctx.report_choices("step", steps, value=resolved)`; choices appear in
  `EvaluationResult.parameters` keyed by the graph parameter name when the node param is bound with
  `$param` (here `"step"`), else by `"<node>.<param>"`, and drive the web step scrubber.
- Keys use the resolved frame content (§5), so `latest` is safe on live runs and step aliases of
  one frame share a cache entry.
- Batch re-render (SimViz): `suan graph run g.json --bind run=DIR --param step=all` evaluates each
  step and writes `<output>.%08d.png` plus an `stk.series/1` manifest `{"schema": "stk.series/1",
  "parameter": "step", "frames": [{"step", "outputs": {name: file}}]}`.
- The graph `time` block (domain, current, range, stride, policy, fps) is the animation context for
  clients; `{"$anim": ...}` keyframes are reserved for a later version.

## 7. View (`stk.view/1`) and camera presets

`stk.view/1`: `camera {projection, frame, position, focal_point, view_up, view_angle_deg,
parallel_scale, zoom, preset}` (float64, physical coordinates, not relative to a render origin),
`preset`, `viewport {width, height, magnification, lock_aspect}`, `background {type, color, color2}`,
`lighting {preset: three_point|headlight|none, intensity}`, `render {engine, samples, transparent}`,
`overlays [{layer, anchor, offset_px, size_px}]`, `visibility {layer: bool}`, `time`.

Camera presets fit the scene bounds (centre c, bounding-sphere radius r, view angle θ):
focal point = c; position = c + u · r / sin(θ/2) / zoom; parallel scale = r / zoom. Directions u
and view-up: `+x` (1,0,0) up z; `-x` (−1,0,0) up z; `+y` (0,1,0) up z; `-y` (0,−1,0) up z; `+z`
(0,0,1) up y; `-z` (0,0,−1) up y; `iso` (1,−1,1)/√3 up z. `+x` means "looking from +x". Numeric
cameras (`position` + `focal_point` [+ `view_up`, default z or y if parallel to z]) override presets.

## 8. Plots (`stk.plot/1`)

Plot nodes build an stk.plot/1 spec (`figure {size_in, dpi, style, title}`, `axes[{id, grid, title,
x, y, y2 {label, unit, scale, range}, legend, grid_lines, aspect, stats}]`, `marks[{type: line|
scatter|bar|hist|heatmap|quiver|errorbar|fill_between, axes, y_axis, data {table, x, y, …, filter[
{column, op, value}], stride, last_n}, style, …}]`, `tables {name: {columns, units}}`). Rendering is
matplotlib `Figure` + `FigureCanvasAgg` only (never pyplot; `MPLCONFIGDIR` under a writable cache
in services) to PNG/SVG(/PDF) plus the plotted data as JSON. Labels default to the column name plus
its unit (`unspecified` shown).

## 9. Evaluation result (`stk.graph-result/1`)

Returned by `suan.graph.service` (agent action `graph.evaluate`, MCP, CLI `--json`):

```json
{"schema": "stk.graph-result/1", "graph_sha256": "<hex>", "graph_hash": "sha256:<hex>", "profile": "web",
 "outputs": {
   "view":     {"type": "payload", "manifest": {"schema": "stk.payload/2", "…": "buffers as \"sha256:<hex>\" uris"},
                "scene_v1": {"…": "only with v1_fallback"}},
   "image":    {"type": "image", "blob": "<sha256>", "media_type": "image/png", "size": 123, "width": 1600,
                "height": 1200},
   "fractions":{"type": "table", "column_names": ["value", "name", "family", "count", "fraction", "color"],
                "columns": {"value": [1, 2], "…": []}, "units": {"fraction": "1"}, "attrs": {}},
   "big":      {"type": "table", "blob": "<sha256>", "media_type": "application/json", "size": 300000,
                "rows": 20000, "column_names": ["step", "Total Energy"]},
   "info":     {"type": "value", "value": {"detected": true}},
   "large":    {"type": "value", "blob": "<sha256>", "media_type": "application/json", "size": 300000},
   "energy":   {"type": "plot", "blob": "<sha256>", "media_type": "image/svg+xml", "size": 1,
                "data_blob": "<sha256 of the plotted data, stk.plot-data/1 JSON>"},
   "export":   {"type": "file", "name": "domains.vtkhdf", "media_type": "application/x-hdf5", "blob": "<sha256>",
                "size": 1},
   "polar":    {"type": "dataset", "descriptor": {"schema": "stk.dataset/1"}}},
 "parameters": {"step": {"value": 1000, "choices": [0, 500, 1000]}},
 "keys": {"polar": {"data": "…", "full": "…"}}, "evaluated": ["polar"], "timings": {"polar": 0.8},
 "cache": {"hits": 5, "misses": 3},
 "warnings": [{"code": "payload_reduced", "message": "Layer 'vol': volume quantized to u16", "path": "/outputs/view",
               "node": "scene", "hint": null, "severity": "warning", "details": {"layer": "vol"}}],
 "errors": [{"code": "frame_not_found", "message": "…", "path": "", "node": "polar", "hint": null,
             "severity": "error", "skipped": ["scene"]}]}
```

`graph_sha256` is the hex digest of `graph_hash`; `profile` is the request profile. `blob` values
are sha256 strings of blobs in the hub blob store (`GET /api/v1/blobs/{sha256}`) or, for the CLI and
MCP, files written next to the result. `scene` outputs are delivered as `payload` (encoded with the
request profile); budget reductions of that encoding are reported as `payload_reduced` warnings
(`node` = the scene node, `path` = the output), like those of `stk.output.payload@1`. Tables whose
JSON exceeds 256 KiB, and such values, are blobs (`rows` = the row count); `column_names` always
gives the table's column order (JSON object order is not reliable across stores and clients). Plots
are delivered in the request's `plot_format` (`svg` default, `png`, `pdf`) with the plotted data as
`data_blob`. `errors` is present only when some requested outputs failed while others were
delivered (the first error lists the outputs it `skipped`); when nothing can be delivered the
request fails with the node's error code (§5).

The request `budget.max_output_bytes` limits the delivered bytes (blobs plus this document) and
defaults to the request profile's payload budget (phone 32 MiB, web 128 MiB, desktop 2 GiB;
`stk-render-payload-v2.md` §7); the evaluation itself has no output-byte limit (in-memory values such
as a full-resolution scene are reduced when encoded). Plots rendered for delivery are memoized by
the plot node's full key and the format, so a warm request renders nothing.

## 10. Presets (content owned by Phase C1, `suan/graph/presets/*.json`)

`slice`, `iso`, `vectors` (reproduce today's `view.build` modes), `volume`, `muferro-domains`,
`muferro-polarization-glyphs`, `energy-plot`. Presets bind a source binding named `run` (muFerro)
or `data` (generic file) and expose `step` plus their main thresholds as graph parameters.

## 11. Validation (`suan.graph.schema.validate_graph(graph, registry, *, parameters=None)`)

Returns `[GraphIssue(code, message, path, node, hint, severity)]`; `path` is an RFC 6901 JSON
Pointer into the graph (e.g. `/nodes/3/params/values`). Never imports NumPy and never runs node
code. `check_graph(...)` raises `GraphValidationError` with all errors.

| code | meaning |
|---|---|
| `invalid_document` | not a JSON object, or not plain JSON (NaN, non-string keys) |
| `schema_version` | `schema` is not `stk.graph/1` |
| `missing_field` | missing graph `schema`/`nodes`/`outputs` or node `id`/`type` |
| `unknown_key` | undefined key (extensions must start with `x-`) |
| `bad_structure` | wrong JSON shape (e.g. `nodes` not a list, bad `time` block) |
| `too_large` | size limits (200 nodes, 256 KiB, 64 KiB params, 64 parameters) |
| `invalid_id` | bad node id, parameter name or output name |
| `duplicate_id` | two nodes share an id |
| `invalid_type_ref` | `type` is not `namespace.family.name@major` |
| `unknown_type` | node type not in the catalog |
| `catalog_version` | graph requires a newer catalog for a namespace |
| `unknown_param` | param not declared by the node type (hint: closest name) |
| `missing_param` | required param absent |
| `invalid_param` | param value violates its schema |
| `invalid_parameter` | malformed graph parameter declaration, default or override |
| `unknown_parameter` | override for an undeclared graph parameter |
| `bad_param_ref` | malformed `$param` or undeclared parameter name |
| `param_ref_type` | a parameter's value violates the schema of a node param referencing it |
| `reserved_key` | other `$` key (e.g. `$anim`) |
| `unknown_input` | input port not declared |
| `bad_link` | malformed link, unknown source node or output port |
| `multi_link` | list of links on a non-multi port |
| `missing_input` | required input not linked |
| `port_mismatch` | incompatible port type or dataset kind |
| `cycle` | links form a cycle (the issue lists the nodes on it) |
| `no_outputs` | empty `outputs` |
| `bad_output` | output names an unknown node/port or a non-deliverable type |

## 12. CLI (Phase B2)

`suan graph catalog [--json]`, `suan graph schema`, `suan graph validate FILE [--param k=v]`,
`suan graph run FILE --bind NAME=DIR|task:ID [--param k=v ...] [--output NAME ...] --out DIR
[--cache DIR] [--profile web]`, `suan graph doctor` (checks offscreen rendering in a subprocess).
`python -m suan.graph` is equivalent. `run` writes `result.json` (with `--param NAME=all`:
`result.<value>.json` per value plus `series.json`) next to the output files; an output whose file
would take one of these names is written as `<name>.output.json` instead. With `NAME=all` the errors
of every failed value are printed (`step=100: error [...]`) and the exit status is 1.

## 13. Milestone-1 node catalog

Generated from `docs/specs/catalog/m1_nodes.py` (the JSON form is `stk-catalog-m1.json`). Types are
listed by id. Ports: `name: type<kinds>`; params: JSON types with bounds, default and stage.
Implementation owners: sources → Phase B1 (`suan/graph/nodes/sources.py`); filters and analysis →
Phase C1 (`suan/graph/nodes/{filters,analysis}.py`, algorithms in `suan/data/filters.py` and
`suan/analysis`); render/view/output/plot → Phase B3 (`suan/graph/nodes/{render,view,output,plot}.py`).
Semantics of the domain nodes are in `domain-classifiers.md`; further per-node rules are in §14.
Params shown as `object` have their full schema in `stk-catalog-m1.json` (`color` is the colour spec
of §4.2; glyph `scale` is `{by: uniform|magnitude|field, field?, factor: number > 0 | "auto"}`).

<!-- catalog:begin (generated by docs/specs/catalog/m1_nodes.py) -->

#### `stk.analysis.film_detect@1` — Film detection / 薄膜检测

Find substrate, film and air layers along z from where the vector field is nonzero. Adds int8 label field (-1 air, 0 substrate, 1 film); 'info' reports the layer indices.

- stage `analysis`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<image> (required)
- outputs: `out`: dataset<labels>, `info`: value<json>

| param | type | default | stage |
|---|---|---|---|
| `field` | field of `in` (name) \| null | `null` | data |
| `component_offset` | integer (>=0, <=4093) | `0` | data |
| `epsilon` | number (>=0) | `1e-06` | data |
| `output` | string (pattern) | `"film"` | data |

#### `stk.analysis.label_fractions@1` — Label fractions / 畴体积分数

Point (or cell) counts and fractions per category; the denominator excludes 'exclude'. 'families' aggregates by category family (e.g. R/O/T).

- stage `analysis`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<labels> (required)
- outputs: `out`: table, `families`: table

| param | type | default | stage |
|---|---|---|---|
| `field` | string (pattern) \| null | `null` | data |
| `exclude` | integer[0..256] | `[-1, 0]` | data |
| `include_empty` | boolean | `true` | data |

#### `stk.analysis.orientation_classify@1` — Orientation classify / 畴取向分类

Label each point with the nearest reference direction (docs/specs/domain-classifiers.md): -1 unclassified/no data, 0 substrate (film detection), 1..N variants.

- stage `analysis`, cache `disk`, time_dependent `false`
- inputs: `in`: dataset<image> (required)
- outputs: `out`: dataset<labels>

| param | type | default | stage |
|---|---|---|---|
| `field` | field of `in` (name) \| null | `null` | data |
| `component_offset` | integer (>=0, <=4093) | `0` | data |
| `direction_set` | enum "stk:cubic-26" \| "stk:cubic-100" \| "stk:cubic-110" \| "stk:cubic-111" \| "custom" | `"stk:cubic-26"` | data |
| `directions` | number[3][1..64] \| null | `null` | data |
| `numbering` | enum "stk" \| "stk-legacy" | `"stk"` | data |
| `min_magnitude` | number (>=0) | `0.1` | data |
| `max_angle_deg` | number (>0, <=180) | `180.0` | data |
| `film_detection` | boolean | `false` | data |
| `film_epsilon` | number (>=0) | `1e-06` | data |
| `output` | string (pattern) | `"domain"` | data |

#### `stk.analysis.statistics@1` — Statistics / 统计

Per field and component: count, nan_count, min, max, mean, std (and magnitude).

- stage `analysis`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<image, polydata, table> (required)
- outputs: `out`: table

| param | type | default | stage |
|---|---|---|---|
| `fields` | string[0..64] \| null | `null` | data |
| `components` | enum "each" \| "magnitude" \| "both" | `"both"` | data |

#### `stk.filter.calculator@1` — Calculator / 计算器

Fixed operations that add one field: magnitude, component, scale, normalize, compose. No expression language in M1.

- stage `data`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<image> (required)
- outputs: `out`: dataset<kind of `in`>

| param | type | default | stage |
|---|---|---|---|
| `operation` | enum "magnitude" \| "component" \| "scale" \| "normalize" \| "compose" | **required** | data |
| `field` | field of `in` (name) \| null | `null` | data |
| `fields` | string[2..16] \| null | `null` | data |
| `component` | integer (>=0) | `0` | data |
| `factor` | number | `1.0` | data |
| `compose_as` | enum "array" \| "vector" | `"array"` | data |
| `result` | string (pattern) \| null | `null` | data |
| `unit` | string \| null | `null` | data |
| `keep_input` | boolean | `true` | data |

#### `stk.filter.contour@1` — Contour / 等值面

Isosurfaces at one or more values (marching cubes / flying edges). Output point field 'iso_value' plus interpolated probe_fields.

- stage `data`, cache `disk`, time_dependent `false`
- inputs: `in`: dataset<image> (required)
- outputs: `out`: dataset<polydata>

| param | type | default | stage |
|---|---|---|---|
| `field` | field of `in` (name or {name, component}) \| null | **required** | data |
| `values` | number[1..32] \| null | `null` | data |
| `compute_normals` | boolean | `true` | data |
| `probe_fields` | string[0..16] \| null | `null` | data |

#### `stk.filter.crop@1` — Crop (VOI) / 裁剪

Extract a volume of interest by inclusive point-index ranges. Origin moves to the first kept point; spacing, fields and categories are kept.

- stage `data`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<image> (required)
- outputs: `out`: dataset<kind of `in`>

| param | type | default | stage |
|---|---|---|---|
| `extent` | integer \| null (>=0)[6] | `[null, null, null, null, null, null]` | data |

#### `stk.filter.glyph_source@1` — Glyph source / 箭头采样

Sample points of a vector field for glyphs: stride or seeded random sampling, magnitude range and label mask, capped at max_points. Point fields: the vector field, 'magnitude' and the listed attributes.

- stage `data`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<image> (required)
- outputs: `out`: dataset<points>

| param | type | default | stage |
|---|---|---|---|
| `field` | field of `in` (name) \| null | `null` | data |
| `sampling` | enum "stride" \| "random" | `"stride"` | data |
| `stride` | integer (>=1)[3] | `[1, 1, 1]` | data |
| `max_points` | integer (>=1, <=5000000) | `5000` | data |
| `seed` | integer (>=0) | `0` | data |
| `magnitude_range` | [number \| null, number \| null] | `[null, null]` | data |
| `mask_field` | string (pattern) \| null | `null` | data |
| `mask_labels` | integer[1..256] \| null | `null` | data |
| `attributes` | string[0..16] \| null | `null` | data |

#### `stk.filter.label_surfaces@1` — Label surfaces / 畴界面

One closed, smoothed surface per label: indicator (label == v) -> contour at 0.5 -> smoothing -> normals. Cell field 'label' (int32) carries the categories.

- stage `data`, cache `disk`, time_dependent `false`
- inputs: `in`: dataset<labels> (required)
- outputs: `out`: dataset<polydata>

| param | type | default | stage |
|---|---|---|---|
| `field` | string (pattern) \| null | `null` | data |
| `labels` | "present" \| integer[1..256] | `"present"` | data |
| `exclude` | integer[0..256] | `[-1, 0]` | data |
| `smoothing` | enum "windowed_sinc" \| "laplacian" \| "none" | `"windowed_sinc"` | data |
| `smooth_iterations` | integer (>=0, <=500) | `30` | data |
| `smooth_factor` | number (>0, <=2) | `0.1` | data |
| `compute_normals` | boolean | `true` | data |
| `close_boundaries` | boolean | `true` | data |

#### `stk.filter.sample@1` — Sample (stride) / 抽样

Keep every n-th point along each axis (spacing multiplied by the stride). With max_points the stride grows uniformly until the point count fits.

- stage `data`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<image> (required)
- outputs: `out`: dataset<kind of `in`>

| param | type | default | stage |
|---|---|---|---|
| `stride` | integer (>=1)[3] | `[1, 1, 1]` | data |
| `max_points` | integer (>=1) \| null | `null` | data |

#### `stk.filter.slice@1` — Slice / 切片

axis mode: the grid plane at an index (exact samples, a 2D image with that axis of size 1; label fields kept). plane mode: an arbitrary plane cut (triangulated polydata, trilinear point data, nearest for label fields).

- stage `data`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<image> (required)
- outputs: `out`: dataset<image, labels, polydata>

| param | type | default | stage |
|---|---|---|---|
| `mode` | enum "axis" \| "plane" | `"axis"` | data |
| `axis` | enum "x" \| "y" \| "z" | `"z"` | data |
| `index` | integer (>=0) \| null | `null` | data |
| `origin` | number[3] \| null | `null` | data |
| `normal` | number[3] | `[0.0, 0.0, 1.0]` | data |
| `fields` | string[0..64] \| null | `null` | data |

#### `stk.filter.streamlines@1` — Streamlines / 流线 (stretch)

Stretch goal. Integrate streamlines of a vector field from seed points on a sphere.

- stage `data`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<image> (required)
- outputs: `out`: dataset<polydata>

| param | type | default | stage |
|---|---|---|---|
| `field` | field of `in` (name) \| null | `null` | data |
| `seed_center` | number[3] \| null | `null` | data |
| `seed_radius` | number (>0) \| null | `null` | data |
| `seed_count` | integer (>=1, <=100000) | `100` | data |
| `direction` | enum "forward" \| "backward" \| "both" | `"forward"` | data |
| `max_length` | number (>0) \| null | `null` | data |
| `seed` | integer (>=0) | `0` | data |

#### `stk.filter.threshold@1` — Threshold / 阈值

Add a uint8 label field (1 inside, 0 outside) selecting lower <= value <= upper (null = unbounded; component null on a vector = magnitude), or a set of labels.

- stage `data`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<image> (required)
- outputs: `out`: dataset<labels>

| param | type | default | stage |
|---|---|---|---|
| `field` | field of `in` (name or {name, component}) \| null | **required** | data |
| `lower` | number \| null | `null` | data |
| `upper` | number \| null | `null` | data |
| `labels` | integer[1..256] \| null | `null` | data |
| `invert` | boolean | `false` | data |
| `output` | string (pattern) | `"mask"` | data |

#### `stk.output.dataset@1` — Dataset export / 数据导出

Write a dataset to VTKHDF (STK profile), VTI or NPY, or a table to CSV/JSON.

- stage `output`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset (required)
- outputs: `file`: file

| param | type | default | stage |
|---|---|---|---|
| `format` | enum "vtkhdf" \| "vti" \| "npy" \| "csv" \| "json" | `"vtkhdf"` | data |
| `name` | string (pattern) \| null | `null` | data |
| `fields` | string[0..64] \| null | `null` | data |
| `precision` | enum "float64" \| "float32" | `"float64"` | data |

#### `stk.output.image@1` — Image / 图片

Render a scene (offscreen VTK in a subprocess) or a plot (matplotlib) to PNG; plots also to SVG/PDF.

- stage `output`, cache `memory`, time_dependent `false`
- inputs: `source`: scene \| plot (required)
- outputs: `image`: image

| param | type | default | stage |
|---|---|---|---|
| `width` | integer (>=16, <=16384) \| null | `null` | client |
| `height` | integer (>=16, <=16384) \| null | `null` | client |
| `magnification` | integer (>=1, <=8) | `1` | client |
| `transparent` | boolean | `false` | client |
| `format` | enum "png" \| "svg" \| "pdf" | `"png"` | client |

#### `stk.output.payload@1` — Render payload / 渲染数据包

Encode a scene as stk.payload/2 within the profile budget (optionally with a scene v1 downgrade).

- stage `output`, cache `memory`, time_dependent `false`
- inputs: `scene`: scene (required)
- outputs: `payload`: payload

| param | type | default | stage |
|---|---|---|---|
| `profile` | enum "auto" \| "phone" \| "web" \| "desktop" | `"auto"` | client |
| `budget` | null \| object | `null` | client |
| `v1_fallback` | boolean | `false` | client |

#### `stk.plot.bar@1` — Bar chart / 柱状图

Bars of value columns per category row (e.g. label fractions).

- stage `plot`, cache `memory`, time_dependent `false`
- inputs: `table`: table (required)
- outputs: `plot`: plot

| param | type | default | stage |
|---|---|---|---|
| `x` | string | **required** | data |
| `y` | string[1..8] | **required** | data |
| `color_column` | string \| null | `null` | data |
| `orientation` | enum "vertical" \| "horizontal" | `"vertical"` | client |
| `log` | boolean | `false` | client |
| `title` | string \| null | `null` | client |
| `size_in` | number (>0, <=100)[2] | `[6.0, 4.0]` | client |
| `dpi` | integer (>=30, <=1200) | `200` | client |

#### `stk.plot.heatmap@1` — Heatmap / 热图

2D slice of an image field as a heatmap (label fields use their categorical palette).

- stage `plot`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<image> (required)
- outputs: `plot`: plot

| param | type | default | stage |
|---|---|---|---|
| `field` | field of `in` (name or {name, component}) \| null | `null` | data |
| `axis` | enum "x" \| "y" \| "z" | `"z"` | data |
| `index` | integer (>=0) \| null | `null` | data |
| `colormap` | string | `"viridis"` | client |
| `range` | [number \| null, number \| null] | `[null, null]` | client |
| `aspect` | enum "equal" \| "auto" | `"equal"` | client |
| `colorbar` | boolean | `true` | client |
| `title` | string \| null | `null` | client |
| `size_in` | number (>0, <=100)[2] | `[6.0, 4.0]` | client |
| `dpi` | integer (>=30, <=1200) | `200` | client |

#### `stk.plot.histogram@1` — Histogram / 直方图

Histogram of a field (image/polydata) or a column (table).

- stage `plot`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<image, polydata, table> (required)
- outputs: `plot`: plot

| param | type | default | stage |
|---|---|---|---|
| `field` | field of `in` (name or {name, component}) \| null | `null` | data |
| `bins` | integer (>=1, <=10000) | `64` | data |
| `range` | [number \| null, number \| null] | `[null, null]` | data |
| `density` | boolean | `false` | data |
| `log` | boolean | `false` | client |
| `color` | string | `"C0"` | client |
| `title` | string \| null | `null` | client |
| `size_in` | number (>0, <=100)[2] | `[6.0, 4.0]` | client |
| `dpi` | integer (>=30, <=1200) | `200` | client |

#### `stk.plot.line@1` — Line plot / 曲线图

Columns against x with an optional second y axis (from 'table2' when linked), row filters and per-column styles (SimViz 1D page).

- stage `plot`, cache `memory`, time_dependent `false`
- inputs: `table`: table (required), `table2`: table (optional)
- outputs: `plot`: plot

| param | type | default | stage |
|---|---|---|---|
| `x` | string \| null | `null` | data |
| `y` | string[1..16] | **required** | data |
| `y2` | string[0..16] | `[]` | data |
| `filters` | object[0..16] | `[]` | data |
| `stride` | integer (>=1) | `1` | data |
| `last_n` | integer (>=1) \| null | `null` | data |
| `x_label` | string \| null | `null` | client |
| `y_label` | string \| null | `null` | client |
| `y2_label` | string \| null | `null` | client |
| `x_scale` | enum "linear" \| "log" \| "symlog" | `"linear"` | client |
| `y_scale` | enum "linear" \| "log" \| "symlog" | `"linear"` | client |
| `y2_scale` | enum "linear" \| "log" \| "symlog" | `"linear"` | client |
| `styles` | object | `{}` | client |
| `legend` | boolean | `true` | client |
| `grid` | boolean | `true` | client |
| `stats` | boolean | `false` | client |
| `title` | string \| null | `null` | client |
| `size_in` | number (>0, <=100)[2] | `[6.0, 4.0]` | client |
| `dpi` | integer (>=30, <=1200) | `200` | client |

#### `stk.render.axes@1` — Axes triad / 坐标轴

Orientation triad overlay (axes_triad).

- stage `representation`, cache `memory`, time_dependent `false`
- inputs: none
- outputs: `layer`: layer

| param | type | default | stage |
|---|---|---|---|
| `labels` | string[3] | `["x", "y", "z"]` | client |
| `anchor` | enum "top_left" \| "top" \| "top_right" \| "left" \| "center" \| "right" \| "bottom_left" \| "bottom" \| "bottom_right" | `"bottom_left"` | client |
| `size_px` | integer (>=16, <=512) | `80` | client |

#### `stk.render.categorical_legend@1` — Categorical legend / 分类图例

Legend of category names and colours, from a categorical layer or a labels dataset.

- stage `representation`, cache `memory`, time_dependent `false`
- inputs: `source`: layer \| dataset<labels> (required)
- outputs: `layer`: layer

| param | type | default | stage |
|---|---|---|---|
| `field` | string (pattern) \| null | `null` | data |
| `only_present` | boolean | `true` | data |
| `title` | string \| null | `null` | client |
| `anchor` | enum "top_left" \| "top" \| "top_right" \| "left" \| "center" \| "right" \| "bottom_left" \| "bottom" \| "bottom_right" | `"right"` | client |
| `columns` | integer (>=1, <=8) | `1` | client |

#### `stk.render.glyphs@1` — Glyphs / 箭头

Instanced glyphs (arrow/cone/sphere/line/cube) at the input points, oriented by a vector field; scale and colour are client-side.

- stage `representation`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<polydata> (required)
- outputs: `layer`: layer

| param | type | default | stage |
|---|---|---|---|
| `vectors` | field of `in` (name) \| null | `null` | data |
| `attributes` | "all" \| string (pattern)[0..64] | `"all"` | data |
| `shape` | enum "arrow" \| "cone" \| "sphere" \| "line" \| "cube" | `"arrow"` | client |
| `resolution` | integer (>=3, <=64) | `8` | client |
| `center` | boolean | `true` | client |
| `scale` | object | `{"by": "magnitude", "factor": "auto"}` | client |
| `color` | object | `{"by": "orientation"}` | client |
| `opacity` | number (>=0, <=1) | `1.0` | client |
| `name` | string \| null | `null` | client |

#### `stk.render.orientation_legend@1` — Orientation legend / 取向色球

The stk:orientation-hsl colour sphere overlay (SimViz orientation legend).

- stage `representation`, cache `memory`, time_dependent `false`
- inputs: none
- outputs: `layer`: layer

| param | type | default | stage |
|---|---|---|---|
| `title` | string \| null | `null` | client |
| `anchor` | enum "top_left" \| "top" \| "top_right" \| "left" \| "center" \| "right" \| "bottom_left" \| "bottom" \| "bottom_right" | `"bottom_right"` | client |
| `size_px` | integer (>=32, <=512) | `120` | client |
| `lightness_range` | number (>=0, <=1)[2] | `[0.0, 1.0]` | client |

#### `stk.render.outline@1` — Outline / 外框

Bounding-box edges of the input as a lines layer.

- stage `representation`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<image, polydata> (required)
- outputs: `layer`: layer

| param | type | default | stage |
|---|---|---|---|
| `color` | number (>=0, <=1)[3] | `[0.0, 0.0, 0.0]` | client |
| `width_px` | number (>=0, <=32) | `1.0` | client |
| `name` | string \| null | `null` | client |

#### `stk.render.scalar_bar@1` — Scalar bar / 色标

Scalar bar overlay explaining the continuous colouring of the linked layer.

- stage `representation`, cache `memory`, time_dependent `false`
- inputs: `source`: layer (required)
- outputs: `layer`: layer

| param | type | default | stage |
|---|---|---|---|
| `title` | string \| null | `null` | client |
| `anchor` | enum "top_left" \| "top" \| "top_right" \| "left" \| "center" \| "right" \| "bottom_left" \| "bottom" \| "bottom_right" | `"right"` | client |
| `orientation` | enum "vertical" \| "horizontal" | `"vertical"` | client |
| `label_count` | integer (>=2, <=20) | `5` | client |
| `format` | string (pattern) | `".3g"` | client |

#### `stk.render.surface@1` — Surface / 表面

Polydata -> triangles (or lines/points) layer; a planar image (one axis of size 1) -> slice_image layer. Attributes travel raw; colouring is client-side.

- stage `representation`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<polydata, image> (required)
- outputs: `layer`: layer

| param | type | default | stage |
|---|---|---|---|
| `attributes` | "all" \| string (pattern)[0..64] | `"all"` | data |
| `color` | object | `{"by": "solid", "solid": [0.8, 0.8, 0.8]}` | client |
| `opacity` | number (>=0, <=1) | `1.0` | client |
| `shading` | enum "smooth" \| "flat" | `"smooth"` | client |
| `edges` | boolean | `false` | client |
| `lighting` | boolean | `true` | client |
| `name` | string \| null | `null` | client |

#### `stk.render.volume@1` — Volume / 体渲染

Dense volume texture with colour and opacity transfer functions (client-side).

- stage `representation`, cache `memory`, time_dependent `false`
- inputs: `in`: dataset<image> (required)
- outputs: `layer`: layer

| param | type | default | stage |
|---|---|---|---|
| `field` | field of `in` (name or {name, component}) \| null | `null` | data |
| `encoding` | enum "auto" \| "u8" \| "u16" \| "f32" | `"auto"` | data |
| `colormap` | string | `"viridis"` | client |
| `range` | [number \| null, number \| null] | `[null, null]` | client |
| `opacity` | [number (>=0, <=1), number (>=0, <=1)][2..64] \| null | `null` | client |
| `sampling` | enum "linear" \| "nearest" | `"linear"` | client |
| `shade` | boolean | `false` | client |
| `name` | string \| null | `null` | client |

#### `stk.source.file@1` — Field file / 场文件

Read a field file inside a binding: MuPRO DAT, NPY, VTI, legacy VTK STRUCTURED_POINTS or VTKHDF (image or polydata).

- stage `source`, cache `disk`, time_dependent `false`
- inputs: none
- outputs: `out`: dataset<image, polydata>

| param | type | default | stage |
|---|---|---|---|
| `binding` | string (pattern) | **required** | data |
| `path` | string (pattern) | **required** | data |
| `format` | enum "auto" \| "dat" \| "npy" \| "vti" \| "vtk" \| "vtkhdf" | `"auto"` | data |
| `fields` | string[0..64] \| null | `null` | data |
| `association` | enum "auto" \| "point" \| "cell" | `"auto"` | data |
| `spacing` | number[3] \| null | `null` | data |
| `origin` | number[3] \| null | `null` | data |
| `length_unit` | string \| null | `null` | data |
| `unit` | string \| null | `null` | data |
| `quantity` | string (pattern) \| null | `null` | data |
| `step` | integer (>=0) \| null | `null` | data |

#### `stk.source.muferro_frame@1` — muFerro frame / muFerro 帧

Read one published field frame '<dataset>.<step:08d>.dat' of a muFerro run as an image dataset (VTK order (z,y,x,c)). Reports the available steps as choices.

- stage `source`, cache `disk`, time_dependent `true`
- inputs: `frames`: table<frames> (required)
- outputs: `out`: dataset<image>

| param | type | default | stage |
|---|---|---|---|
| `dataset` | string (pattern) | `"Polar"` | data |
| `step` | integer (>=0) \| enum "latest" \| "first" | `"latest"` | data |
| `policy` | enum "latest_at_or_before" \| "exact" | `"latest_at_or_before"` | data |
| `spacing` | number[3] \| null | `null` | data |
| `origin` | number[3] \| null | `null` | data |
| `length_unit` | string | `"grid_index"` | data |
| `unit` | string | `"unspecified"` | data |
| `quantity` | string (pattern) \| null | `null` | data |
| `precision` | enum "float64" \| "float32" | `"float64"` | data |

#### `stk.source.muferro_run@1` — muFerro run / muFerro 计算

Index of a muFerro run directory: published field frames, the energy trace, the progress log and the derived stk.result/1 manifest.

- stage `source`, cache `memory`, time_dependent `true`
- inputs: none
- outputs: `frames`: table<frames>, `energy`: table, `progress`: table, `result`: value<json>

| param | type | default | stage |
|---|---|---|---|
| `binding` | string (pattern) | **required** | data |
| `case_dir` | string (pattern) | `"auto"` | data |

#### `stk.source.table@1` — Table file / 表格文件

Read a table file inside a binding: muFerro energy_out.dat, whitespace columns (optional header), CSV or a progress JSONL log.

- stage `source`, cache `memory`, time_dependent `false`
- inputs: none
- outputs: `out`: table

| param | type | default | stage |
|---|---|---|---|
| `binding` | string (pattern) | **required** | data |
| `path` | string (pattern) | **required** | data |
| `format` | enum "auto" \| "muferro_energy" \| "columns" \| "csv" \| "progress_jsonl" | `"auto"` | data |
| `columns` | string[0..256] \| null | `null` | data |
| `units` | object | `{}` | data |

#### `stk.view.camera@1` — Camera / 相机

A preset (fit to the scene bounds) or a numeric camera in physical coordinates.

- stage `view`, cache `memory`, time_dependent `false`
- inputs: none
- outputs: `camera`: camera

| param | type | default | stage |
|---|---|---|---|
| `preset` | enum "iso" \| "+x" \| "-x" \| "+y" \| "-y" \| "+z" \| "-z" \| null | `"iso"` | client |
| `position` | number[3] \| null | `null` | client |
| `focal_point` | number[3] \| null | `null` | client |
| `view_up` | number[3] \| null | `null` | client |
| `projection` | enum "perspective" \| "parallel" | `"perspective"` | client |
| `view_angle_deg` | number (>0, <180) | `30.0` | client |
| `zoom` | number (>0) | `1.0` | client |
| `parallel_scale` | number (>0) \| null | `null` | client |

#### `stk.view.scene@1` — Scene / 场景

Ordered layers plus the view (camera, viewport, background, lighting).

- stage `view`, cache `memory`, time_dependent `false`
- inputs: `layers`: layer (required, multi), `camera`: camera (optional)
- outputs: `scene`: scene

| param | type | default | stage |
|---|---|---|---|
| `background` | number (>=0, <=1)[3] | `[1.0, 1.0, 1.0]` | client |
| `lighting` | enum "three_point" \| "headlight" \| "none" | `"three_point"` | client |
| `width` | integer (>=16, <=16384) | `1600` | client |
| `height` | integer (>=16, <=16384) | `1200` | client |
| `render_origin` | "auto" \| number[3] | `"auto"` | client |
| `title` | string \| null | `null` | client |

<!-- catalog:end -->

## 14. Node semantics (details beyond the catalog)

Unless stated otherwise: input fields are kept (zero-copy), coordinates are physical float64
(`direction` applied), non-finite samples never count as data, and a node that produces nothing
(empty contour, empty slice) returns an empty dataset and warns (`empty_result`).

**Sources**

- `muferro_run`: uses the `mupro.muferro` connector (`describe(live=True)`). `case_dir: "auto"` (the
  default) is the `case_dir` the STK launcher recorded in `stk-mupro.json` at the binding root (runs
  submitted with `suan mupro submit --input DIR` keep their case in `DIR/`), else `"."`; an unsafe
  recorded path also gives `"."`. `frames` columns: `dataset` (string stem), `step` (int64), `time`
  (float64, NaN = unknown), `path` (string, relative to the binding), `size` (int64), `sha256`
  (string, `""` if not computed; informational), `reader` (string, `mupro.dat@1`), `components`
  (int64); attrs `{binding, case_dir (resolved), complete}`. On a live view the newest frame of a stem
  whose size differs from the frame before it is left out (muFerro is still writing it; frames of a
  stem are fixed-width, so all have one size). `energy` and `progress` as in `stk-data-format-v1.md`
  §14 (before the first row, or without a header, the energy columns keep muFerro's names);
  `result` is the stk.result/1 manifest. Fingerprint: the resolved `case_dir`, the (path, size,
  mtime) listing of frame files plus the sha256 of `energy_out.dat`, `mupro_progress.jsonl`,
  `mupro_completion.json`, `stk-mupro.json` and the case's `*.toml` files when present.
- `muferro_frame`: picks rows with `dataset` = the stem, resolves `step` with `policy` (unknown →
  `frame_not_found`) and reports the steps as choices. Output `ImageData` (id = stem) with one point
  field named after the stem, `time.step` = the resolved step, provenance `used` = the file. Geometry:
  spacing/origin overrides else 1/0 with `length_unit` (default `grid_index`); `unit` and `quantity`
  (default from the connector, e.g. Polar → `polarization`) apply to the field. `precision:
  "float32"` marks the field `lossy`. Fingerprint `{path, sha256, reader, components}` with the
  sha256 of the file as it is now (`FileSource.sha256`, memoized by path, size, mtime and inode;
  never the frames table's column, which may come from a cached index or another run with the same
  listing); two steps resolving to one file share a cache entry. Rows the DAT reader cannot parse
  (e.g. a frame being written) are `invalid_data`.
- `file`: `format: auto` by extension (`.dat`, `.npy`, `.vti`, `.vtk`, `.vtkhdf`/`.hdf`/`.h5` with
  a `/VTKHDF` group). NPY holds `(x, y, z)` or `(x, y, z, c)` like today's `read_field`. VTI/VTK honour
  the `STK_units`, `STK_coordinate_units`, `STK_timestep` FieldData of `scene.load_grid`; VTKHDF
  honours the `/STK` descriptor. Default `length_unit`: `grid_index` for DAT/NPY, else from the file
  or `unspecified`. `unit`/`quantity` override every loaded field. Fingerprint `{path, sha256, format}`.
- `table`: `muferro_energy` (`kt: N energy: e1..e5` rows), `columns` (whitespace, optional header
  row, `#`/`!` comments), `csv` (header required), `progress_jsonl` (one object per line; columns =
  union of keys). Column units from `units`, else `unspecified` (`normalized` for muFerro energy).

**Filters**

- `crop`: output dimensions `(i1−i0+1, …)`, origin = `point(i0, j0, k0)`, point and cell fields
  cropped (C-contiguous copies); lo > hi after clipping → `invalid_param`.
- `sample`: keeps indices 0, s, 2s, … per axis (the last point is not forced), spacing × s. With
  `max_points`, s grows by the smallest integer factor f ≥ 1 with Π ceil(n_i / (s_i f)) ≤ max_points.
- `calculator`: `magnitude` → ‖v‖ (float64, unit kept, name `<field>_magnitude`); `component` →
  `field[..., component]` (name `<field>_<component name or index>`); `scale` → field × `factor`
  (unit = `unit` param, else the input unit if factor = 1, else `unspecified`); `normalize` → v/‖v‖
  (0 where ‖v‖ = 0, unit `1`); `compose` → stacks the scalar `fields` in order (tensor `compose_as`;
  `vector` needs 2 or 3 fields and names x, y, z; `array` uses the field names; unit = the common
  unit or `unspecified`). `result` overrides the name; `keep_input: false` keeps only the result.
- `slice`: axis mode — `index` null → n // 2; output image with that axis of size 1, origin moved,
  exact samples, label fields kept (kind `labels` if any). Plane mode — `origin` null → bounds centre;
  `normal` normalized (zero → `invalid_param`); triangulated polydata with trilinear point data and
  nearest-sample label fields.
- `threshold`: s = the selected component, or the magnitude when `component` is null on a
  multi-component field; inside ⇔ lower ≤ s ≤ upper (null = unbounded); for label fields with
  `labels`, inside ⇔ value ∈ labels. `invert` flips; NaN is outside. Adds uint8 label field
  `output` with categories `0 "outside"`, `1 "inside"`, palette `stk:categorical`.
- `contour`: scalar selection as for threshold; `values` null → one value at (min + max)/2 of the
  finite data. Output triangles with point field `iso_value` (float64), `Normals` (float32 × 3) when
  `compute_normals`, and `probe_fields` interpolated trilinearly.
- `glyph_source`: candidates = grid points on the stride lattice (stride grows like `sample` when
  over `max_points`), filtered by `magnitude_range` (inclusive) and by the mask (`mask_field` value in
  `mask_labels`, or nonzero when `mask_labels` is null). `random` draws min(max_points, candidates)
  without replacement with `numpy.random.default_rng(seed)` (output in draw order); `stride` keeps
  grid order (x fastest). Output points polydata with point fields: the vector field (name kept,
  tensor vector), `magnitude` (float64) and `attributes`; `attrs["sample_spacing"]` = the smallest
  physical spacing × effective stride.
- `label_surfaces`: `domain-classifiers.md` §7.

**Analysis**: `orientation_classify`, `film_detect`, `label_fractions`: `domain-classifiers.md`
§3–§5. `statistics`: rows per field and component (`components: each|magnitude|both`; magnitude
rows only for multi-component fields); columns `field` (string), `component` (string: component
name, index or `magnitude`), `count` (finite values, int64), `nan_count` (non-finite, int64), `min`,
`max`, `mean`, `std` (population, ddof 0; float64), `unit` (string). String columns are skipped.

**Render** (layer values and payload mapping are defined by `stk-render-payload-v2.md`)

- `surface`: polydata with polygons → `triangles` layer (polygons triangulated); lines only →
  `lines`; points only → `points`. An image with exactly one dimension of size 1 → `slice_image`
  (plane origin = first sample, u/v along the other two axes in x, y, z order); any other image →
  `not_planar` (hint: add `stk.filter.slice`). `attributes: "all"` sends every point/cell field with
  ≤ 4 components (others skipped with a warning); label fields become categorical attributes with
  their palette. `color.by: "field"` with `field` null uses the first attribute.
- `glyphs`: `instances` layer; directions = `vectors` (first 3-component field when null); scale
  `uniform` → factor, `magnitude` → factor × |v|, `field` → factor × field; `factor: "auto"` →
  0.8 × `sample_spacing` / max |v| (magnitude) or 0.8 × `sample_spacing` (uniform), falling back to
  0.05 × the bounds diagonal. Default colour: `orientation` with `max_magnitude` = max |v|.
- `volume`: the selected scalar is encoded `u8`/`u16` linearly over the finite [min, max]
  (`value_scale` = (max − min)/(2^bits − 1), `value_offset` = min) or `f32` raw; `auto` = u8 (phone),
  u16 (web), f32 (desktop). Over the voxel budget the volume is strided and the reduction recorded.
  Label fields force `nearest` sampling and their palette. Built-in colormaps: `viridis`, `cividis`,
  `coolwarm`, `turbo`, `gray`. Opacity points are `[x, alpha]` with x normalized over `range`;
  `opacity: null` (the default) is `[[0, 0], [1, 0.8]]` for scalars and, for label fields, alpha 0.8
  for every label ≥ 0 and 0 for negative labels (−1 = unclassified/air), so no present category
  disappears (`stk-render-payload-v2.md` §6.6). A layer's `pick.probe.node` is the source node of
  the dataset's provenance when it is upstream of the layer in the evaluated graph, else the layer's
  own node (clients walk upstream to the source).
- `outline`: the 12 edges of the grid box (oriented by `direction`) or of the polydata bounds.
- `scalar_bar`: colormap and range of the source layer's continuous colouring after `finalize`;
  title default `<field> [<unit>]`; a categorical source warns (`use_legend`).
- `categorical_legend`: entries from the source's categories (layer attribute palette or the
  dataset's label field); `only_present` lists values present in the data except −1 (none present:
  an empty legend and an `empty_result` warning). Render nodes keep an empty result drawable: an
  empty polydata becomes an empty `triangles` layer with its point and cell attributes.
- `axes`, `orientation_legend`: overlays `axes_triad` and `orientation_legend`.

**View**: `camera` → the camera object of §7. `scene`: layers in link order, camera default preset
`iso`, `width`/`height` → viewport; `render_origin: "auto"` = the centre of the bounds of the first
image dataset feeding the layers (stable across the frames of one grid), else the centre of the union
of layer bounds.

**Output**

- `payload`: encodes the scene (`stk-render-payload-v2.md`) within the profile budget (`profile:
  "auto"`, the default, is the request profile, see §5; `budget` overrides individual limits);
  `v1_fallback` also attaches a scene v1 downgrade
  (`suan/render/v1.py`), delivered as `"scene_v1"` next to the manifest.
- `image`: a scene is rendered by offscreen VTK **in a subprocess** from its desktop-profile payload
  at `width` × `height` (default: the scene viewport) × `magnification` (PNG, RGBA if `transparent`);
  a plot by matplotlib (pixel width/height override `size_in` at the spec's dpi). `svg`/`pdf` are
  plot-only (`unsupported` for scenes). A PNG plot is refused above 16384² pixels
  (`suan.plot.mpl.MAX_PIXELS`) before matplotlib allocates it; the control hub reviews images and PNG
  plots above 7680 × 4320 pixels before they run.
- `dataset`: `vtkhdf` (any M1 kind, STK profile), `vti` (image), `npy` (image, `(x, y, z, c)` like
  `read_field`), `csv`/`json` (tables). File `<name or node id>.<ext>`; value `{name, media_type,
  sha256, size, path}` with a disk cache, else `{name, media_type, sha256, size, bytes}`. The file
  is written to a private temporary file, `sha256`/`size` are those of the bytes written, and it
  is renamed to the content-addressed `<scratch>/exports/<sha256>/<name>` (concurrent evaluations
  never collide). Scratch space counts towards the cache's disk budget and is pruned least recently
  used; a request whose cached export file was pruned re-runs the export node.

**Plot**

- `line`: `x` null → the table's index column, else the first column; rows kept where all `filters`
  hold, then `stride`, then `last_n`; `y` on the left axis, `y2` on the right (from `table2` when
  linked); `styles` per column; `stats` adds a min/max/mean box. Axis labels default to the column
  name and unit.
- `heatmap`: the plane at `index` (null → middle) normal to `axis`, the two other axes in x, y, z
  order with physical extents; label fields use their palette and a legend instead of a colour bar.
- `histogram`: finite values of the selected field/column; `range` null → data range.
- `bar`: one bar per row of `x`, grouped by `y` columns; colours from `color_column` when given.
