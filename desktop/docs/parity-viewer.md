# Viewer parity checklist (WP10)

中文摘要：本清单对照 SimViz（旧 Qt+VTK 查看器）与网页查看器（`web/src`），逐项列出桌面查看器
（Viewer / Properties / Probe 编辑器与导出对话框）的对应功能与状态。“完成”表示已实现并有测试覆盖；
“部分”表示已有替代方案但未完全等价；“推迟”注明计划的里程碑。

The desktop Viewer replaces SimViz and matches the web viewer. SimViz rebuilt one hand-coded VTK
pipeline from its Qt widgets; STK expresses the same views as `stk.graph/1` presets that run next to
the data, and the desktop shows the returned `stk.payload/2`. Parity is therefore judged on what the
user can see and do, not on SimViz's widgets.

Status: **done** (implemented and tested), **partial** (an equivalent exists with gaps, noted), **deferred**
(milestone named). Tests are under `desktop/tests/app` (`stk_app_viewer_tests`, `stk_app_viewer_gpu_tests`,
`app_viewer_e2e_*`, `app_viewer_window_*`, `app_viewer_gui_open_*`).

## SimViz (Qt + VTK, `SimpleView.cxx`)

| # | SimViz feature | Desktop equivalent | Status |
|---|---|---|---|
| S1 | Open DAT / legacy VTK files (scalar, vector, domain modes) | Open a run folder (File > Open, drag and drop, Jobs "Open in viewer"); the `slice`, `iso`, `volume`, `vectors` presets read DAT/NPY/VTI/VTK/VTKHDF through a `data` binding, the muFerro presets through `run` | done |
| S2 | Refresh (rebuild the whole pipeline) | Parameter edits re-evaluate automatically (debounced; a newer edit cancels the running evaluation with `graph.cancel`); "Evaluate" button; only the affected nodes re-run (node cache) | done |
| S3 | Scalar volume rendering (ray cast, transfer functions) | `volume` preset, ray-marched volume layer in `stk_viewer_gpu`; colormap, value range and opacity curve editor with numeric control points, add/remove, automatic mode and reset | done |
| S4 | Slice (cutter with origin / normal) | `slice` preset (axis, index, component, colormap) | partial (axis-aligned slices; arbitrary planes: catalog `stk.filter.slice@1`, no preset field yet) |
| S5 | Isosurfaces, one per value with its colour | `iso` preset (`levels` list, colormap, opacity) | partial (multi-isosurface UI with per-level colours: deferred, M-D2) |
| S6 | Vector glyphs (mask, magnitude threshold, scale, colour modes) | `vectors` / `muferro-polarization-glyphs` presets (stride, max arrows, `\|P\|` threshold), instanced glyphs, orientation legend | done |
| S7 | Streamlines | catalog `stk.filter.streamlines@1` (stretch) | deferred (no preset in M1) |
| S8 | Ferroelectric domains: 26-variant classifier, film detection, smoothed label surfaces, per-variant colours | `muferro-domains` preset (threshold, max angle, film detection, smoothing iterations), categorical legend; e2e golden + VTK cross-check | done |
| S9 | VO2 M1/M2 classifier | not in the M1 catalog | deferred |
| S10 | Editable colormap control points / opacity tables | Colormap dropdown fed by `colormaps.list` (gradient swatches); volume opacity editor for 2–64 control points with preview | partial (opacity tables done; custom colour control points remain deferred, M-D2) |
| S11 | Per-domain / per-actor opacity | Sidebar "Layers": opacity slider per layer (display override, kept across steps) | done |
| S12 | Grid rescale (dx, dy, dz) | Source metadata (`origin` / `spacing`) of `stk.source.file@1` | partial (not a form field) |
| S13 | Region of interest and sample rate | catalog `stk.filter.crop@1`, `stk.filter.sample@1`; vector presets expose `stride` | partial |
| S14 | Camera: 6 axis presets + isometric | Sidebar "Camera": iso, ±X, ±Y, ±Z (numpad 1 / 3 / 7 / 0 like Blender), and the presets' `view` parameter | done |
| S15 | Numeric camera (position, focal point, view-up) | Sidebar "Numeric camera": position and focal point in physical coordinates (float64), view-up, view angle, parallel projection and scale | done |
| S16 | Fixed viewport size for deterministic output | Export dialog width / height (default: the result's viewport); `--size` headless | done |
| S17 | PNG export with an integer magnification, RGBA | Export dialog ×1–×8 (tiled), transparent background, overlays on/off; `--magnification`, `--transparent`, `--no-overlays` headless | done |
| S18 | X3D scene export | — | deferred (not planned for D1) |
| S19 | Save / load the view state ("output/load status") | Layout file keeps the Viewer's tool, navigation style and lighting; graph + parameters are the preset document | partial (camera and parameters are not yet saved with the layout) |
| S20 | Batch 3D: loop over steps, one image each | Export dialog "All time steps": `<stem>.%08d.png` + `stk.series/1` manifest; `--sequence` headless | done |
| S21 | Decorations: outline box, axes, scalar bars, orientation sphere | Payload overlays drawn by `stk_viewer_gpu`; "Overlays" toggle in the header | done |
| S22 | 1D plots (QCustomPlot) | presets deliver plots; the desktop requests only payload outputs | deferred (plots panel, M-D2) |
| S23 | Rotate ±X / ±Y / ±Z actions | Camera presets, orbit tool, numpad 9 (opposite side) | done |
| S24 | Editable scalar-bar titles | `stk.render.scalar_bar@1` client params (not exposed by the presets) | deferred |

## Web viewer (`web/src`: `GraphPanel.tsx`, `PayloadViewer.tsx`, `Legend.tsx`)

| # | Web feature | Desktop equivalent | Status |
|---|---|---|---|
| W1 | Preset picker (`graph.presets`) | Properties "Preset" dropdown (localized names), description, data-source bindings | done |
| W2 | Parameter editor per preset (step: latest / first / number) | Form generated from JSON Schema (`stk_ui` `preset_schema` + `build_form`), grouped by `x-stk-group`; data-stage and client-stage boxes; goldens for all 7 presets in zh and en | done |
| W3 | Step scrubber (‹ › latest, "i / n"), 300 ms debounce, camera kept | Sidebar "Time steps": scrubber, first / previous / play-pause / next / last, fps, loop, latest; cached steps switch without a bridge call (measured below), neighbours prefetched and uploaded ahead; camera kept across steps | done |
| W4 | Layer visibility chips | Sidebar "Layers" checkboxes (plus opacity) | done |
| W5 | Reset view ("复位视角") | Camera "Reset" (the result's camera) and "View all" (Home) | done |
| W6 | Stats line (triangles / glyphs / voxels / KiB) | Bottom of the view | done |
| W7 | Payload warnings (collapsible) | "⚠ N warning(s)" at the bottom of the view, details in its tooltip | done |
| W8 | Click picks, drag rotates (4 px threshold) | Same rule in every tool; float64 refinement of the GPU pick | done |
| W9 | Physical-coordinate probe with editable position, "query original value" | Probe editor: layer, element, physical position (`format_label`), editable position with "Query original value", components, magnitude, units, interpolation (bridge `probe`) | done |
| W10 | Open a local `.stkp` | File > Open, drag and drop, `--open` (also payload folders, CLI result folders and series) | done |
| W11 | Progress / status line | Progress bar from `graph.progress` (node, done / total), cancel button; last evaluation summary (nodes, data nodes, seconds, cache) | done |
| W12 | Superseded evaluations abandoned | The running evaluation is cancelled (`graph.cancel`) when a newer edit starts one | done |
| W13 | Overlays: scalar bar, legend, orientation sphere, triad, text | `stk_viewer_gpu` overlays (BLF, CJK) | done |
| W14 | Plots, tables, images of the result | Only payload outputs are requested | deferred (M-D2 plots panel) |
| W15 | Hub review wait ("等待复核") | Hub evaluations in review show a status; evaluate again after approval | partial (no automatic re-wait) |

## Desktop additions

- Blender-style navigation by default (middle drag orbit, Shift pan, Ctrl zoom; left button uses the toolbar
  tool: orbit / pan / zoom / pick), ParaView style optional (left orbit, middle pan, right zoom).
- Playback with fps and loop; neighbour prefetch (evaluation in the background and GPU upload ahead).
- `stk-desktop --headless --preset muferro-domains --run DIR --export out.png [--size] [--camera]
  [--param k=v] [--magnification N] [--sequence]` — the WP12 end-to-end golden.
- Lighting override (as the result asks, three-point, headlight, none).

## Measurements (this host, lavapipe / llvmpipe)

Recorded by `stk_app_viewer_gpu_tests` (`METRIC` lines) and `run_e2e.py`:

- Client-stage change (`view` iso → +x): evaluated `camera`, `scene`; 0 data nodes; view re-rendered (26 % of the pixels changed).
- Data-stage change (`min_magnitude`): data nodes `domains`, `surfaces` re-ran.
- Cached step switch (2 → 1): 0.4 ms in the viewer state, 5.7 ms including GPU `set_payload` and a 400×300 render
  (budget 300 ms); a revisit through the bridge's node cache: about 30 ms, 0 nodes evaluated.
- End-to-end golden: SSIM 1.000 against the committed golden (Vulkan and OpenGL); VTK offscreen reference:
  domain mask IoU 0.995 (SSIM 0.979 with overlays).
