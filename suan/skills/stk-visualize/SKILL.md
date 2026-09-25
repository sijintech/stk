---
name: stk-visualize
description: Visualize and quantify STK simulation results (muFerro phase-field runs first) with STK node graphs - start from a preset, edit parameters, validate, then render or evaluate next to the data, and report numbers with their thresholds and units.
---

# STK visualization with node graphs

STK describes every figure as a node graph (`stk.graph/1`): source nodes read a run, filter and analysis
nodes transform it, render nodes turn data into layers, a scene node assembles them, and output nodes
deliver a render payload (`stk.payload/2`), a PNG, plots (`stk.plot/1`) or tables. Graphs are evaluated
where the data lives and cached, so changing only appearance parameters is cheap.

Tools (MCP server `stk-toolkit`): `list_tasks`, `get_task`, `list_artifacts`, `get_task_events`,
`graph_catalog`, `graph_validate`, `graph_evaluate`, `graph_render`, `plot_table`.
The same operations exist on the command line: `suan graph catalog | validate | run | doctor`.
`reference/nodes.md` lists every node type with its ports and parameters; `examples/` holds complete graphs.

## Workflow

1. **Find the run.** `list_tasks` / `get_task`: use a task whose state is `succeeded` (only finished tasks
   publish files). `list_artifacts` shows what it wrote; muFerro frames are `<Stem>.<step:08d>.dat`
   (`Polar.00000200.dat`), plus `energy_out.dat` and the launcher record `stk-mupro.json`. For a running task,
   use the `stk-monitor` skill instead of guessing progress.
2. **Start from a preset or an example, not from scratch.** `graph_catalog` lists the presets (with their
   bindings and parameters) and the node types. Examples in `examples/`:
   `muferro-domains` (cubic-26 domain variants, legend, fractions, energy plot),
   `muferro-polarization-glyphs` (arrows coloured by direction), `muferro-polarization-isosurface`
   (|P| isosurfaces plus statistics), `muferro-polarization-volume` (|P| volume with a colour bar),
   `muferro-energy-plot` (energy terms against step).
3. **Bind the data and edit parameters.** Graphs never contain filesystem paths: a source names a *binding*
   (for example `run`) and paths *inside* it. Bind at evaluation time:
   `{"run": {"task_id": "<32-hex task id>"}}` (or `{"run": {"dir": "/path"}}` for a run directory on this
   host). Prefer changing graph-level `parameters` (e.g. `{"step": 200, "min_magnitude": 0.1}`) over editing
   nodes. `step` accepts an integer, `"latest"` or `"first"`; the result reports the chosen step and all
   available steps (`parameters.step.choices`). Parameters with stage `client` (colormap, opacity, glyph scale,
   camera) change appearance only; stage `data` parameters re-run the affected nodes.
4. **Validate.** `graph_validate(graph=..., parameters=...)` (or `preset=...`). Every error has a `code`, a
   JSON-pointer `path`, the `node` and a `hint`; fix the graph and validate again until `valid` is true.
5. **Render or evaluate.**
   - `graph_render` returns a PNG of the graph's image output (or of its first scene). It needs offscreen
     OpenGL; when it reports that rendering is unavailable, use `graph_evaluate` and hand the payload to a
     viewer, or show the plots.
   - `graph_evaluate(..., outputs=[...])` writes every requested output to files and returns a summary:
     payload directory (`manifest.json` + buffers), images, plots (SVG/PNG plus `*.data.json` with the plotted
     numbers), and tables (inlined when small).
   - Through the STK hub the same request is the action `graph.evaluate` with payload
     `{"preset": "muferro-domains", "bindings": {"run": {"task_id": "…"}}, "parameters": {"step": 200},
     "outputs": ["payload", "fractions", "energy_plot"], "profile": "web"}`; bigger budgets go to review.
6. **Report honestly** (see below). Quote numbers from tables, statistics, probes and plot data files.

## Reporting rules

- **Never infer physics from colours.** Colours come from a colormap or palette; read values from
  `statistics`, `label_fractions`, the plot `data_file`, or a probe. Say which output a number came from.
- **State every threshold you used**: e.g. `min_magnitude = 0.1` (points with |P| at or below it are
  unclassified), `max_angle_deg` (points whose best angle is not below it are unclassified), isovalues, glyph
  stride and `max_points` (glyphs are a sample, not every point).
- **Units are never guessed.** `unspecified` means the unit is unknown — write "unspecified units", not a
  physical unit. `normalized` (muFerro energies) stays normalized; `1` means dimensionless; `grid_index`
  lengths are grid points, not nanometres unless the run declares a spacing and length unit.
- **Label semantics** in domain maps and fractions: `-1` = unclassified / no data (below the magnitude
  threshold, outside the film, air), `0` = substrate, `1…26` = the cubic-26 variants (T 1–6, O 7–18,
  R 19–26 in STK numbering; each variant is followed by its antiparallel partner). Fractions exclude -1 and 0
  by default: report the denominator (classified points, or all points) and the unclassified count.
- Report the step (and whether it was `latest`), the task id, warnings from the result (e.g.
  `payload_reduced`: the payload was decimated to meet the device budget), and any `errors` for outputs that
  failed while others were delivered.
- A run that has not finished may lack frames; a frame older than the requested step is used under the
  `latest_at_or_before` policy — say so when the reported step differs from the requested one.

## Minimal example

```json
{"schema": "stk.graph/1", "catalog": {"stk": 1},
 "parameters": [{"name": "step", "type": "step", "default": "latest"}],
 "nodes": [
  {"id": "run", "type": "stk.source.muferro_run@1", "params": {"binding": "run"}},
  {"id": "polar", "type": "stk.source.muferro_frame@1", "inputs": {"frames": {"from": "run.frames"}},
   "params": {"dataset": "Polar", "step": {"$param": "step"}}},
  {"id": "box", "type": "stk.render.outline@1", "inputs": {"in": {"from": "polar.out"}}},
  {"id": "volume", "type": "stk.render.volume@1", "inputs": {"in": {"from": "polar.out"}}},
  {"id": "scene", "type": "stk.view.scene@1",
   "inputs": {"layers": [{"from": "volume.layer"}, {"from": "box.layer"}]}},
  {"id": "payload", "type": "stk.output.payload@1", "inputs": {"scene": {"from": "scene.scene"}}},
  {"id": "energy_plot", "type": "stk.plot.line@1", "inputs": {"table": {"from": "run.energy"}},
   "params": {"x": "step", "y": ["Total Energy"]}}],
 "outputs": {"payload": "payload.payload", "energy_plot": "energy_plot.plot", "energy": "run.energy"}}
```

Evaluate it with `graph_evaluate(graph=<above>, bindings={"run": {"task_id": "<id>"}}, parameters={"step": "latest"})`.
