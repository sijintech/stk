# STK data format v1: data model, units, manifests, VTKHDF profile and connectors

> 中文摘要：本文档定义 STK 统一数据格式 v1：数据集种类（M1 实现 image、polydata、table 及 image 上的分类标签）、
> 字段描述（关联方式、类型、分量、张量、UCUM 单位与 quantity 标签）、时间帧、坐标系、溯源与数据引用；
> 以及磁盘容器 VTKHDF + STK 附加信息、结果清单 `stk.result/1`、算例清单 `stk.case/1` 和连接器接口。单位从不猜测：`unspecified` ≠ `1`。

Status: frozen for Milestone 1 (Phase A). Machine contracts: `suan/contracts/schemas/{field-1,
dataset-1,result-1,case-1,ref-1}.schema.json` and `suan/contracts/quantities.json`. In-memory model:
`suan/data/model.py`. Connector protocols: `suan/connectors/api.py`.

## 1. Principles

- **Data stays where it was computed.** Graphs go to the data; payloads come back.
- **Immutable things are identified by sha256** (files, published frames, blobs, cache entries).
- **Units are never guessed.** `unspecified` is displayed as such and blocks conversion; it is not `1`.
- **Colours are not measurements.** Numbers come from probing the original data.
- **Every contract is a JSON Schema** in `suan/contracts/schemas/` (draft 2020-12, `$id`
  `urn:stk:schema:<name>`). `suan.contracts` loads them with the standard library only
  (`list_schemas()`, `load_schema("graph-1" | "stk.graph/1")`, `load_all_schemas()`,
  `load_quantities()`, `quantity_info(name, tensor=None)`). `jsonschema` is not a dependency;
  Python validation of graphs is hand-written (`suan.graph.schema`).

## 2. Dataset kinds

| kind | meaning | VTKHDF `Type` | M1 |
|---|---|---|---|
| `image` | uniform grid: point dimensions, origin, spacing, 3×3 direction | ImageData | implemented |
| `rectilinear` | one coordinate array per axis | RectilinearGrid | specified |
| `structured` | curvilinear points (nx, ny, nz, 3) | StructuredGrid | specified |
| `unstructured` | points + typed VTK cells (FEM), parts and sets | UnstructuredGrid | specified |
| `polydata` | vertices, lines, polygons | PolyData | implemented |
| `particles` | atoms/particles, optional bonds and periodic cell | PolyData + STK particles profile | specified |
| `table` | named typed columns | Table | implemented |
| `collection` | named tree of datasets | PartitionedDataSetCollection | specified |

Refinements used by graph port checks (`suan.graph.registry.DATASET_KINDS`): `labels` ⊂ `image`
(an image with at least one label field), `points` ⊂ `polydata` (no lines and no polygons),
`frames` ⊂ `table` (columns `dataset`, `step`, `path`, ...).

Not kinds: a volume/density is an `image` with a quantity such as `electron_density`; **time** is a
list of frames on any dataset; sparse/AMR grids (HyperTreeGrid, OpenVDB) are deferred (VDB appears
only in render payloads later).

## 3. Field descriptor (`field-1`)

| key | required | meaning |
|---|---|---|
| `name` | yes | 1–128 characters, no `/` or `.` (VTKHDF restriction) |
| `association` | yes | `point`, `cell`, `field` (whole dataset) or `row` (table column) |
| `dtype` | yes | `float64 float32 int64 int32 int16 int8 uint64 uint32 uint16 uint8 string` (`string` only for `row`/`field`) |
| `components` | yes | ≥ 1 |
| `tensor` | yes | `scalar` (1), `vector` (2 or 3), `symmetric_tensor` (6), `tensor` (4 or 9), `quaternion` (4), `array` (components of unknown meaning), `label` (1, integer dtype) |
| `unit` | yes | UCUM code or a reserved token (§4) |
| `component_names` | for symmetric_tensor, tensor, quaternion | explicit order, e.g. `["xx","yy","zz","yz","xz","xy"]`; length = `components`. Vectors default to x, y, z. **Component order is never assumed.** |
| `quantity` | no | vocabulary id or `namespace:name` (§4) |
| `normalization` | no | `{reference_value, reference_unit, note}` for `unit: "normalized"` |
| `categories` | for `label` | `[{value, name, direction?, color?, family?, aliases?, description?}]`, unique values |
| `palette` | no | palette id (`stk:categorical`, `stk:cubic-26-orientation`, `stk-legacy:ferro27`) |
| `range` / `magnitude_range` | no | per-component `[min, max]` / `[min, max]` of the magnitude; filled lazily, never required |
| `role` | no | table columns: `index`, `time`, `value`, `label`, `coordinate` |
| `description`, `lossy` | no | `lossy: true` marks down-converted display caches (e.g. float32) |

Label fields: reserved values `-1` = unclassified or no data, `0` = substrate/background (see
`domain-classifiers.md` §1). Renderers never interpolate labels.

## 4. Units and quantities

- `unit` is a **UCUM case-sensitive code**: `C/m2`, `V/m`, `J/m3`, `nm`, `Ao` (ångström), `eV`, `K`,
  `GPa`, `fs`, `/m3`. Reserved tokens (`suan.contracts.UNIT_TOKENS`):
  - `unspecified` — unknown; the default everywhere; blocks conversion; shown to users and reported
    by tools as "unit unspecified".
  - `1` — dimensionless.
  - `normalized` — solver-native normalized value; optional `normalization` block.
  - `grid_index` — lengths only: coordinates are grid indices (scene v1 wrote `"grid index"`; the
    `ImageData.to_grid`/`from_grid` adapters translate).
- `quantity` comes from `suan/contracts/quantities.json` (`stk.quantities/1`). Each entry has
  `label {en, zh}`, `dimension` (SI base exponents L, M, T, I, Theta, N), `si_unit`, default `tensor`,
  `components`, optional `component_names`, and display hints `representation`
  (`glyphs|slice|iso|volume|label_surfaces|line_plot`), `colormap`, `range`
  (`data|symmetric|nonnegative|unit`), `categorical` and `default_graph` (a preset name). Ids:
  polarization, magnetization, electric_field, electric_potential, electric_displacement,
  charge_density, electron_density, strain, eigenstrain, stress, pressure, displacement, velocity,
  force, force_density, energy, energy_density, temperature, concentration, composition,
  order_parameter, density, label, domain_variant, crystal_orientation, time, step, length.
  Namespaced extensions (`mupro:landau_force`) fall back to `defaults` resolved by tensor type.
  Hints never change data or imply a unit.

## 5. Geometry and coordinate frames

- **image** geometry: `dimensions` = point counts `[nx, ny, nz]`; `origin` (float64); `spacing`
  (> 0); `direction` = row-major 3×3 whose **columns** are the axis unit vectors (VTK convention,
  default identity); physical point = origin + direction · (i·dx, j·dy, k·dz). Point fields have
  one value per point; cell fields one per cell, with `max(n−1, 1)` cells along each axis.
- **polydata** geometry: `points` (count), `verts`, `lines`, `polys` (cell counts), `bounds`.
- **table** geometry: `rows`.
- Every spatial dataset names a coordinate `frame` (default `grid`) and a `length_unit`.
  Frames are declared once per manifest (`frames_of_reference`):
  `{"grid": {"length_unit": "grid_index"}, "lab": {"length_unit": "nm"}, "dft_cell":
  {"length_unit": "Ao", "parent": "lab", "transform": [[1,0,0,12.5],[0,1,0,0],[0,0,1,3],[0,0,0,1]]}}`.
  Transforms are float64 row-major 4×4 affines to the parent frame. Multi-scale placement is a frame
  transform, never baked into coordinates. Positions stay float64 in data; only render payloads
  switch to float32 relative to `render_origin`.

## 6. Time and frames

- An in-memory dataset is **one frame**: `time = {step, time, unit}` (`suan.data.model.TimeInfo`).
- A dataset descriptor may list its frames: `frames: [{step, time, index?, sources: {<field> | "*":
  {path, reader, selector?, size?, sha256?, media_type?}}}]`. A field missing from a frame's
  `sources` does not exist at that step (muFerro writes different stems at different steps).
- `path` is POSIX and relative to the run/binding root (no leading `/`, no drive letter, no `..`).
  `reader` is `<id>@<major>` (e.g. `mupro.dat@1`, `mupro.energy@1`, `vtk.vti@1`, `stk.vtkhdf@1`).
  `selector` addresses data inside a container: `"/t00001000/Polar"` (MuPRO HDF5) or
  `{"time_index": 3}` (VTKHDF with steps).
- `sha256` may be `null` while a run is live; once filled, the frame is immutable (a `frame` event,
  `stk-events-v1.md`, means "published").
- Frame selectors (`ref-1` `frame_selector`): `{"step": N}`, `{"latest": true}`, `{"first": true}`,
  `{"index": i}` (negative from the end), `{"follow": "time"}` (graph time), with optional
  `"policy": "latest_at_or_before"` (default: the latest frame whose step ≤ N that has the field) or
  `"exact"` (error `frame_not_found` if missing).

## 7. Identity, provenance and references

- A materialized dataset is identified by `sha256:<file hash>`; a derived in-memory dataset by its
  graph data key (`stk-graph-v1.md` §5).
- Provenance: `{"activity": {"kind": "run|graph|import|convert", "id"}, "agent": {"connector":
  "mupro.muferro@0.1.0", "reader": "mupro.dat@1", "node": "<graph node id>", "stk": "<version>"},
  "used": [{"path", "sha256", "role"}], "derived_from": ["sha256:..."], "generated_at": "<RFC 3339>"}`.
- References (`ref-1`) are the only way tools point at data:
  - `{"run": {"node": "<32hex>", "task": "<32hex>"}, "dataset": "Polar", "field": "Polar", "frame": {"step": 1000}}` — a Runtime task on a node.
  - `{"binding": "run", "path": "Polar.00001000.dat"}` — the **only** form inside graphs: a binding
    name resolved by the caller (`{task_id}` for agent/MCP, a local directory for the CLI) plus a
    relative path. Graphs never contain filesystem paths.
  - `{"file": {"path": "C:/proj/film.vtkhdf"}, "dataset": "film"}` — desktop-local; never evaluated
    on compute nodes.
  - `{"content": "sha256:<hex>", "dataset": "film"}` — pinned in the hub blob store.

## 8. In-memory model (`suan/data/model.py`)

NumPy is imported lazily: descriptors, `Field`, `Category`, `TimeInfo`, `FrameRef`, `Provenance`,
`CoordinateFrame`, metadata-only datasets and `dataset_from_descriptor` work without NumPy.

**Layouts (frozen):**

| dataset | field association | array shape | notes |
|---|---|---|---|
| `ImageData` | point | `(nz, ny, nx, nc)` C-contiguous | VTK order (x fastest): zero-copy to VTK/VTKHDF |
| `ImageData` | cell | `(max(nz−1,1), max(ny−1,1), max(nx−1,1), nc)` | |
| `PolyData` | point / cell | `(n_points, nc)` / `(n_cells, nc)` | cells ordered verts, lines, polys |
| `Table` | row | `(n_rows,)` if nc = 1 else `(n_rows, nc)` | `string` columns hold `str` |

Key API (see docstrings for details):

```python
Field(name, association="point", dtype="float64", components=1, tensor="scalar", unit="unspecified",
      component_names=None, quantity=None, normalization=None, categories=None, palette=None,
      range=None, magnitude_range=None, role=None, description=None, lossy=False, values=None)
  .validate() .to_json() .from_json(d, values=None) .is_label .category(value) Field.dtype_name(array)
Category(value, name, direction=None, color=None, family=None, aliases=(), description=None)
Dataset(id, *, kind=None, fields=(), time=None, frames=(), provenance=None, attrs=None, label=None,
        geometry=None)                      # metadata-only for kinds other than the M1 three
  .add(field) .field(name) .fields .label_fields() .kinds() .descriptor() .copy() .nbytes
ImageData(dimensions, origin=(0,0,0), spacing=(1,1,1), direction=IDENTITY, *, frame="grid",
          length_unit="unspecified", id="image", **dataset_kw)
  .add_field(name, values, *, association="point", layout="zyxc"|"xyzc", tensor=None, **meta)
  .array(name, layout="zyxc") .xyz(name)    # (x, y, z, c) view, no copy
  .shape_zyx .cell_dimensions .point(i, j, k) .bounds() .kinds()  # {"image"} or {"image", "labels"}
  .to_grid(name=None) -> suan.visualization.scene.Grid     ImageData.from_grid(grid, ...)
CellArray(offsets, connectivity)  CellArray.uniform((n, k) array)  CellArray.empty()
PolyData(points=None, *, verts=None, lines=None, polys=None, frame="grid", length_unit=..., id=...)
  PolyData.from_triangles(points, triangles) .add_field(name, values, association="point"|"cell")
  .n_points .n_cells .bounds() .kinds()     # {"polydata"} or {"polydata", "points"}
Table(id="table", *, index=None)  Table.from_columns({name: values}, units=..., quantities=..., index=...)
  .add_column(name, values, unit="unspecified", **meta) .column(name) .n_rows .columns .to_json()
dataset_from_descriptor(descriptor) -> Dataset          json_safe(value)
```

`tensor` defaults to `scalar` (one component), `label` (when `categories` are given) or `array`
(several components: meaning never assumed). JSON outputs of numbers use `json_safe`: non-finite
floats become the strings `"NaN"`, `"Inf"`, `"-Inf"` (same convention as events).

## 9. Dataset descriptor (`stk.dataset/1`)

```json
{"schema": "stk.dataset/1", "id": "Polar", "kind": "image",
 "geometry": {"frame": "grid", "length_unit": "grid_index", "dimensions": [64, 64, 32],
              "origin": [0, 0, 0], "spacing": [1, 1, 1], "direction": [1,0,0, 0,1,0, 0,0,1]},
 "fields": [{"name": "Polar", "association": "point", "dtype": "float64", "components": 3,
             "tensor": "vector", "component_names": ["x", "y", "z"], "quantity": "polarization",
             "unit": "unspecified"}],
 "time": {"index": "step", "step": 1000, "value": null, "physical": {"unit": "unspecified", "known": false}},
 "frames": [{"step": 1000, "time": null,
             "sources": {"Polar": {"path": "Polar.00001000.dat", "reader": "mupro.dat@1"}}}],
 "provenance": {"activity": {"kind": "run", "id": "<task id>"},
                "agent": {"connector": "mupro.muferro@0.1.0", "reader": "mupro.dat@1"}}}
```

Tables use `columns` instead of `fields` (each a field-1 with `association: "row"`).

## 10. On-disk container: VTKHDF + STK profile

Converted, derived and newly written data use **VTKHDF 2.x** written with h5py (`h5py` joins the
`visualization` extra in Phase B). Files must open in `vtkHDFReader` of the pinned `vtk` wheel (a
conformance test checks it). Native formats stay readable through connectors; conversion is never
required. Rejected as main format: XDMF (sidecar drift, cannot transpose), Zarr (no mesh semantics
or VTK reader), OpenUSD (render format; later export), extxyz and H5MD (import/export only).

**ImageData** (`/VTKHDF`):

- attributes `Version` = `[2, 0]` (int64; the conformance test may raise it to the minimum the pinned
  `vtkHDFReader` requires), `Type` = `"ImageData"` written as a fixed-length ASCII
  string (`numpy.bytes_`; some VTK versions reject variable-length strings), `WholeExtent` =
  `[0, nx−1, 0, ny−1, 0, nz−1]` (int64), `Origin` (3 × float64), `Spacing` (3 × float64),
  `Direction` (9 × float64, row-major).
- `PointData/<name>`: shape `(nz, ny, nx)` for one component, `(nz, ny, nx, nc)` otherwise — the
  in-memory layout, so writing needs no transform. `CellData/<name>` likewise with cell counts.
  `FieldData/<name>` for small arrays.
- Chunks 64³ (clipped to the dimensions) × all components, `shuffle` + `gzip` level 4. Float64 is
  kept; float32 only for display caches flagged `stk_lossy`.

**PolyData** (`/VTKHDF`, `Type` = `"PolyData"`): `NumberOfPoints` [n], `Points` (n, 3) float64;
groups `Vertices`, `Lines`, `Polygons`, `Strips`, each with `NumberOfCells` [c],
`NumberOfConnectivityIds` [m], `Offsets` (c + 1, int64), `Connectivity` (m, int64); `PointData`,
`CellData` shaped `(n[, nc])`.

**Table** (`Type` = `"Table"`, the VTKHDF table layout of recent VTK releases): `RowData/<column>` shaped
`(rows[, nc])`; string columns as variable-length UTF-8; `NumberOfRows` = `[rows]` (int64 dataset
under `/VTKHDF`) — `vtkHDFReader` needs it to read a table. STK reads and writes it with h5py
regardless of VTK support.

**`vtkHDFReader` caveats** (checked with VTK 9.3.1 and 9.7.0):

- ImageData with `ny = 1` or `nz = 1` (2D frames, e.g. a 64×64×1 slice) cannot be read: the reader
  reports the dimensions but no point or cell arrays. Such files are valid STK VTKHDF (STK reads
  them back with h5py), but ParaView and other VTK readers show an empty grid; export 2D frames as
  VTI (`stk.output.dataset@1`, `format: "vti"`) when they must open in ParaView.
- VTK 9.3 does not know the `Table` type ("HDF dataset type unknown"); VTK 9.7 reads STK tables
  (the conformance test skips on VTK < 9.4). Image `Direction` is honoured by both versions.

**STK profile** (ignored by VTK):

- Per array (dataset attributes): `stk_unit`, `stk_quantity`, `stk_tensor`,
  `stk_component_names` (JSON), `stk_categories` (JSON), `stk_lossy` (bool).
- File-root group `/STK` with attribute `descriptor` = the stk.dataset/1 JSON (fields without
  values) and attribute `profile` = `1`. Particles later add `/STK/cell`, `/STK/pbc`, `/STK/species`;
  FE sets go to `/STK/sets/{point,cell}/<name>`.
- One file per frame (no SWMR append to files readers may have open). Time series may be
  consolidated afterwards (VTKHDF `Steps`), not in M1.
- On Lustre/NFS set `HDF5_USE_FILE_LOCKING=FALSE`.

**MuPRO HDF5** (`run.h5:/tNNNNNNNN/<name>`) is `(nx, ny, nz, nc)` with x slowest: readers
transpose to `(nz, ny, nx, nc)` (one copy).

**Internal cache format** (not interchange): `.npy` per array plus a JSON descriptor for images;
`.npz` for polydata and tables.

## 11. Result manifest (`stk.result/1`)

Produced by `Connector.describe(run, live=False)`; in M1 derived on demand from the run directory
(TaskSpec and policy templates unchanged). Invariant: *manifest = fold(events) + files +
verification*. Keys: `schema`, `producer {connector, connector_version, stk, generated_at}`,
`complete`, `run {app {id, name, version, executable_sha256}, runtime {node_id, task_id,
workspace_id}, case {case_id, dir, manifest}, layout {ranks, threads_per_rank, launcher},
started_at, finished_at, exit_code}`, `state` (`prepared queued running succeeded failed cancelled
interrupted unknown`), `outcome {classification, retryable, reason}`, `scientific_status`,
`verification {verifier, status, checks[{id, status: pass|fail|warn|skip, message, classification}]}`,
`frames_of_reference`, `qoi[{name, value, unit, quantity, step, time, source {dataset, column,
field, path}, definition}]` (non-finite values as strings), `datasets[]` (stk.dataset/1),
`files[{path, sha256, size, media_type, role}]`, `native[{path, schema}]`, `extensions`.

Mapping from existing manifests:

| `stk-mupro.json` (schema 1) | muprosdk `result.json` (0.1) | `stk.result/1` |
|---|---|---|
| `app`, `state` | `app`, `state` | `run.app`, `state` |
| `classification`, `reason` | `error.{code, classification}` | `outcome` |
| `case_dir`, `case{...}` | `case_id` | `run.case`, `extensions.mupro.case` |
| `layout`, `program.sha256`, `command`, `environment` | executable digest | `run.layout`, `run.app.executable_sha256`, `extensions.mupro` |
| `verification` | implicit | `verification` (same shape) |
| `qoi{total_energy, step}` | `qoi[...]` | `qoi[]` (list, plus `quantity`) |
| `frames[{stem, step, components, path}]` | `fields[{path, shape, unit, layout}]` | `datasets[].fields` + `datasets[].frames[].sources` |
| — | `files[...]`, `scientific_status` | `files[]` (adds `role`, `media_type`), `scientific_status` |

## 12. Case manifest (`stk.case/1`)

`{schema, app, connector {id, version}, parameters_schema {id, sha256, source}, parameters,
inputs[{role, target, writer, from: ref-1}], native {format, entry, files[{path, sha256,
generated}]}, case_id, resources {suggested, constraints[{rule, message}]}, provenance {created_by,
derived_from}}`.

- The connector converts JSON parameters ⇄ native files; STK never parses native syntax, so the
  `.inp` vs TOML question stays per connector.
- `case_id` = `"sha256:" + sha256(canonical_json({"app": app, "files": sorted([{path, sha256}])}))`
  over the native files (`canonical_json` from `suan.graph.schema`). STK's own formula; not promised
  to equal muprosdk's id.
- Parameter schemas are JSON Schema 2020-12 with form annotations `x-stk-unit`, `x-stk-quantity`,
  `x-stk-group`, `x-stk-advanced`, `x-stk-widget` (`int3`, `vector3`, `matrix6x6_voigt`,
  `expression`, `file`, `dataset_ref`) and `x-stk-default-source: "solver"`. Solver defaults are
  shown, never silently applied.

## 13. Connector interface (`suan/connectors/api.py`, `API_VERSION = 1`)

Standard library only; heavy imports inside methods.

- `FileSource`: `list(prefix="") -> Iterable[FileInfo(path, size, mtime)]`, `open(path) -> BinaryIO`
  (seekable), `local_path(path) -> Path | None` (zero-copy on the same host), `sha256(path) -> str`
  (cached by path, size, mtime).
- `DatasetHandle`: `descriptor` (stk.dataset/1), `read(*, frame, fields=None, region=None,
  stride=None) -> Dataset`, `stats(*, frame, field) -> dict`. `region = ((i0, i1), (j0, j1), (k0,
  k1))` inclusive point indices and `stride = (sx, sy, sz)` are pushdown hints: the result must equal
  crop-then-sample of the full frame.
- `Connector` (heavy half, group `stk.connectors`): `id`, `version`, `api`, `info()`, `sniff(run) ->
  Match | None` (names and headers only, < 100 ms), `describe(run, *, live=False) -> stk.result/1`,
  `open(run, dataset_id) -> DatasetHandle`, `verify(run) -> dict | None`,
  `monitor_adapter(run, case) -> MonitorAdapter | None`, `default_graphs(result) -> [stk.graph/1]`.
- `InputConnector` (light half, group `stk.inputs`): `input_schema(app)`, `read_case(case:
  FileSource) -> stk.case/1`, `write_case(case, out_dir) -> [{path, sha256, generated}]`,
  `validate_case(case_dir) -> [{id, status, message}]`, `task_spec(case, resources, **opts) -> dict`.
- `MonitorAdapter.poll(*, final=False) -> [{"type", "data"}]` (events without envelope).
- `Resolver.resolve(binding) -> FileSource` (graph bindings; implemented by `suan.graph.resolve`).
- `ConnectorError(message, code)`; `ENTRY_POINT_GROUPS = {"connectors": "stk.connectors", "inputs":
  "stk.inputs", "nodes": "stk.nodes"}`.

`info()`:

```json
{"id": "mupro.muferro", "version": "0.1.0", "api": 1, "apps": ["mupro.muferro"], "priority": 0,
 "license": "MIT",
 "capabilities": {"read": ["image", "table"], "inputs": {"schema": "mupro.muferro/input@1", "read": true,
                  "write": true}, "verify": "stk-mupro-1", "monitor_adapter": true, "task_spec": true,
                  "default_graphs": ["muferro-domains", "energy-plot"]},
 "runs_on": {"describe": "node", "read": "node|desktop", "inputs": "any", "monitor_adapter": "task"}}
```

Registration: when two connectors claim one id the higher `priority` wins (private `stk-mupro` uses
10) and diagnostics list both; the node configuration's `connectors.allow` (e.g. `["stk.*",
"mupro.*"]`) limits what runs, and the agent reports enabled `{id, version}` pairs.

| part | runs on |
|---|---|
| `input_schema / read_case / write_case / validate_case / task_spec` | Windows desktop, hub, MCP |
| `sniff / describe / open / verify` | the node-agent (Runtime) host, or the desktop for local files |
| `monitor_adapter` | inside the task, in the connector launcher (`python -m suan.mupro run`) |
| heavy batch reads | Runtime tasks on compute nodes |

## 14. Reference mapping: muFerro (public connector `mupro.muferro`)

- `sniff`: `stk-mupro.json`, `mupro_completion.json`, `<Stem>.<8 digits>.dat` (the existing
  `suan.mupro.run.FRAME` pattern), or `input.toml` with `[system].simulation_grid`.
- Datasets: `Polar` and one per auxiliary stem, all `image` on the shared `grid` frame
  (`length_unit: "grid_index"`, spacing 1, origin 0 unless the case says otherwise). Component counts
  from `suan.mupro.run.COMPONENTS`; 3 components → `vector` (x, y, z) for `Polar`
  (`quantity: polarization`) and force/field stems; 6-component stems (`Strain`, `Stress`,
  `Eigen_St`, `Elast_St`) are `tensor: "array"` until MuPRO confirms the Voigt order. Units
  `unspecified` (Polar = P·p0 in C/m² is an open owner question). Reader `mupro.dat@1`; values are
  point samples.
- `energy_out.dat` → table `energy` (reader `mupro.energy@1`): `step` (int64, role index) plus the
  native header names (`Elastic Energy`, `Electric Energy`, `Landau Energy`, `Gradient P Energy`,
  `Total Energy`; `energy_1..5` without a header), float64, `unit: "normalized"`, quantity `energy`.
- `mupro_progress.jsonl` → table `progress` (`step`, `completed_steps`, `total_steps`).
- `verify` wraps `suan.mupro.run.verify_run` (`stk-mupro-1`).
- The full muFerro parameter schema belongs to MuPRO (installed with the SDK); the public connector
  ships a minimal schema for the keys STK reads.
