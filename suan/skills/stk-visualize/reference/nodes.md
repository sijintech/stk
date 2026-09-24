# STK graph node reference

Generated from the node catalog (`stk.catalog/1`) by `python -m suan.skills.reference`; `suan skills export` regenerates it from the installed catalog. Do not edit by hand.

Conventions: links are written on the input side as `{"from": "<node>.<port>"}` (a list for multi ports); a param may be `{"$param": "<graph parameter>"}`. Stage `data` params re-run the node and everything downstream; stage `client` params only change appearance. Units are never guessed: `unspecified` means unknown, `1` means dimensionless. Label values: -1 = unclassified / no data, 0 = substrate.

## Families

- **source** — read data through connectors; a `binding` names the run, `path` is relative inside it: `stk.source.file@1`, `stk.source.muferro_frame@1`, `stk.source.muferro_run@1`, `stk.source.table@1`
- **filter** — transform datasets (data-stage params re-run them): `stk.filter.calculator@1`, `stk.filter.contour@1`, `stk.filter.crop@1`, `stk.filter.glyph_source@1`, `stk.filter.label_surfaces@1`, `stk.filter.sample@1`, `stk.filter.slice@1`, `stk.filter.streamlines@1`, `stk.filter.threshold@1`
- **analysis** — derive labels, fractions and statistics: `stk.analysis.film_detect@1`, `stk.analysis.label_fractions@1`, `stk.analysis.orientation_classify@1`, `stk.analysis.statistics@1`
- **render** — turn data into draw layers; appearance params are client-stage: `stk.render.axes@1`, `stk.render.categorical_legend@1`, `stk.render.glyphs@1`, `stk.render.orientation_legend@1`, `stk.render.outline@1`, `stk.render.scalar_bar@1`, `stk.render.surface@1`, `stk.render.volume@1`
- **view** — camera and scene assembly: `stk.view.camera@1`, `stk.view.scene@1`
- **output** — deliverables: payload, image, dataset export: `stk.output.dataset@1`, `stk.output.image@1`, `stk.output.payload@1`
- **plot** — stk.plot/1 figures (matplotlib), delivered as SVG/PNG plus the plotted data: `stk.plot.bar@1`, `stk.plot.heatmap@1`, `stk.plot.histogram@1`, `stk.plot.line@1`

## `stk.source.file@1` — Field file

Read a field file inside a binding: MuPRO DAT, NPY, VTI, legacy VTK STRUCTURED_POINTS or VTKHDF (image or polydata).

- Inputs: none
- Outputs: `out` (dataset)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `binding` | string | **required** | data | binding |
| `path` | string | **required** | data | Relative path; path |
| `format` | "auto" \| "dat" \| "npy" \| "vti" \| "vtk" \| "vtkhdf" | "auto" | data |  |
| `fields` | array of string \| null | null | data | Arrays to load (default all) |
| `association` | "auto" \| "point" \| "cell" | "auto" | data |  |
| `spacing` | array[3] of number \| null | null | data |  |
| `origin` | array[3] of number \| null | null | data |  |
| `length_unit` | string \| null | null | data |  |
| `unit` | string \| null | null | data |  |
| `quantity` | string \| null | null | data |  |
| `step` | integer (≥0) \| null | null | data | Time step metadata |

## `stk.source.muferro_frame@1` — muFerro frame

Read one published field frame '<dataset>.<step:08d>.dat' of a muFerro run as an image dataset (VTK order (z,y,x,c)). Reports the available steps as choices.

- Inputs: `frames` (table; kinds frames)
- Outputs: `out` (dataset)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `dataset` | string | "Polar" | data | Field stem |
| `step` | integer (≥0) \| "latest" \| "first" | "latest" | data | Step; step |
| `policy` | "latest_at_or_before" \| "exact" | "latest_at_or_before" | data | Step policy |
| `spacing` | array[3] of number \| null | null | data | Spacing override |
| `origin` | array[3] of number \| null | null | data | Origin override |
| `length_unit` | string | "grid_index" | data | Length unit |
| `unit` | string | "unspecified" | data | Field unit |
| `quantity` | string \| null | null | data | Quantity override |
| `precision` | "float64" \| "float32" | "float64" | data |  |

## `stk.source.muferro_run@1` — muFerro run

Index of a muFerro run directory: published field frames, the energy trace, the progress log and the derived stk.result/1 manifest.

- Inputs: none
- Outputs: `frames` (table), `energy` (table), `progress` (table), `result` (value)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `binding` | string | **required** | data | Run binding; binding |
| `case_dir` | string | "." | data | Case directory; path |

## `stk.source.table@1` — Table file

Read a table file inside a binding: muFerro energy_out.dat, whitespace columns (optional header), CSV or a progress JSONL log.

- Inputs: none
- Outputs: `out` (table)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `binding` | string | **required** | data | binding |
| `path` | string | **required** | data | path |
| `format` | "auto" \| "muferro_energy" \| "columns" \| "csv" \| "progress_jsonl" | "auto" | data |  |
| `columns` | array of string \| null | null | data | Columns to keep (default all) |
| `units` | object | {} | data | Column units |

## `stk.filter.calculator@1` — Calculator

Fixed operations that add one field: magnitude, component, scale, normalize, compose. No expression language in M1.

- Inputs: `in` (dataset; kinds image)
- Outputs: `out` (dataset)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `operation` | "magnitude" \| "component" \| "scale" \| "normalize" \| "compose" | **required** | data |  |
| `field` | string \| object {name} \| null | null | data | Input field; field |
| `fields` | array of string \| null | null | data | compose: input fields |
| `component` | integer (≥0) | 0 | data |  |
| `factor` | number | 1.0 | data |  |
| `compose_as` | "array" \| "vector" | "array" | data |  |
| `result` | string \| null | null | data | Result field name |
| `unit` | string \| null | null | data | Result unit |
| `keep_input` | boolean | true | data |  |

## `stk.filter.contour@1` — Contour

Isosurfaces at one or more values (marching cubes / flying edges). Output point field 'iso_value' plus interpolated probe_fields.

- Inputs: `in` (dataset; kinds image)
- Outputs: `out` (dataset)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `field` | string \| object {name, component} | **required** | data | Field; field |
| `values` | array of number \| null | null | data | Isovalues (null = range midpoint) |
| `compute_normals` | boolean | true | data |  |
| `probe_fields` | array of string \| null | null | data |  |

## `stk.filter.crop@1` — Crop (VOI)

Extract a volume of interest by inclusive point-index ranges. Origin moves to the first kept point; spacing, fields and categories are kept.

- Inputs: `in` (dataset; kinds image)
- Outputs: `out` (dataset)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `extent` | array[6] of integer \| null | [null, null, null, null, null, null] | data | [i0, i1, j0, j1, k0, k1] |

## `stk.filter.glyph_source@1` — Glyph source

Sample points of a vector field for glyphs: stride or seeded random sampling, magnitude range and label mask, capped at max_points. Point fields: the vector field, 'magnitude' and the listed attributes.

- Inputs: `in` (dataset; kinds image)
- Outputs: `out` (dataset)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `field` | string \| object {name} \| null | null | data | Vector field; field |
| `sampling` | "stride" \| "random" | "stride" | data |  |
| `stride` | array[3] of integer (≥1) | [1, 1, 1] | data |  |
| `max_points` | integer (≥1, ≤5000000) | 5000 | data |  |
| `seed` | integer (≥0) | 0 | data |  |
| `magnitude_range` | [number \| null, number \| null] | [null, null] | data |  |
| `mask_field` | string \| null | null | data |  |
| `mask_labels` | array of integer \| null | null | data |  |
| `attributes` | array of string \| null | null | data |  |

## `stk.filter.label_surfaces@1` — Label surfaces

One closed, smoothed surface per label: indicator (label == v) -> contour at 0.5 -> smoothing -> normals. Cell field 'label' (int32) carries the categories.

- Inputs: `in` (dataset; kinds labels)
- Outputs: `out` (dataset)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `field` | string \| null | null | data | Label field (null = first) |
| `labels` | "present" \| array of integer | "present" | data |  |
| `exclude` | array of integer | [-1, 0] | data |  |
| `smoothing` | "windowed_sinc" \| "laplacian" \| "none" | "windowed_sinc" | data |  |
| `smooth_iterations` | integer (≥0, ≤500) | 30 | data |  |
| `smooth_factor` | number (>0, ≤2) | 0.1 | data |  |
| `compute_normals` | boolean | true | data |  |
| `close_boundaries` | boolean | true | data |  |

## `stk.filter.sample@1` — Sample (stride)

Keep every n-th point along each axis (spacing multiplied by the stride). With max_points the stride grows uniformly until the point count fits.

- Inputs: `in` (dataset; kinds image)
- Outputs: `out` (dataset)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `stride` | array[3] of integer (≥1) | [1, 1, 1] | data |  |
| `max_points` | integer (≥1) \| null | null | data |  |

## `stk.filter.slice@1` — Slice

axis mode: the grid plane at an index (exact samples, a 2D image with that axis of size 1; label fields kept). plane mode: an arbitrary plane cut (triangulated polydata, trilinear point data, nearest for label fields).

- Inputs: `in` (dataset; kinds image)
- Outputs: `out` (dataset)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `mode` | "axis" \| "plane" | "axis" | data |  |
| `axis` | "x" \| "y" \| "z" | "z" | data |  |
| `index` | integer (≥0) \| null | null | data | Index (null = middle) |
| `origin` | array[3] of number \| null | null | data | Plane origin (null = centre) |
| `normal` | array[3] of number | [0.0, 0.0, 1.0] | data | Plane normal |
| `fields` | array of string \| null | null | data |  |

## `stk.filter.streamlines@1` — Streamlines

Stretch goal. Integrate streamlines of a vector field from seed points on a sphere.

*Stretch goal: may be absent from an install.*

- Inputs: `in` (dataset; kinds image)
- Outputs: `out` (dataset)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `field` | string \| object {name} \| null | null | data | field |
| `seed_center` | array[3] of number \| null | null | data |  |
| `seed_radius` | number (>0) \| null | null | data |  |
| `seed_count` | integer (≥1, ≤100000) | 100 | data |  |
| `direction` | "forward" \| "backward" \| "both" | "forward" | data |  |
| `max_length` | number (>0) \| null | null | data |  |
| `seed` | integer (≥0) | 0 | data |  |

## `stk.filter.threshold@1` — Threshold

Add a uint8 label field (1 inside, 0 outside) selecting lower <= value <= upper (null = unbounded; component null on a vector = magnitude), or a set of labels.

- Inputs: `in` (dataset; kinds image)
- Outputs: `out` (dataset)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `field` | string \| object {name, component} | **required** | data | Field; field |
| `lower` | number \| null | null | data |  |
| `upper` | number \| null | null | data |  |
| `labels` | array of integer \| null | null | data |  |
| `invert` | boolean | false | data |  |
| `output` | string | "mask" | data |  |

## `stk.analysis.film_detect@1` — Film detection

Find substrate, film and air layers along z from where the vector field is nonzero. Adds int8 label field (-1 air, 0 substrate, 1 film); 'info' reports the layer indices.

- Inputs: `in` (dataset; kinds image)
- Outputs: `out` (dataset), `info` (value)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `field` | string \| object {name} \| null | null | data | field |
| `component_offset` | integer (≥0, ≤4093) | 0 | data |  |
| `epsilon` | number (≥0) | 1e-06 | data |  |
| `output` | string | "film" | data |  |

## `stk.analysis.label_fractions@1` — Label fractions

Point (or cell) counts and fractions per category; the denominator excludes 'exclude'. 'families' aggregates by category family (e.g. R/O/T).

- Inputs: `in` (dataset; kinds labels)
- Outputs: `out` (table), `families` (table)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `field` | string \| null | null | data |  |
| `exclude` | array of integer | [-1, 0] | data |  |
| `include_empty` | boolean | true | data |  |

## `stk.analysis.orientation_classify@1` — Orientation classify

Label each point with the nearest reference direction (docs/specs/domain-classifiers.md): -1 unclassified/no data, 0 substrate (film detection), 1..N variants.

- Inputs: `in` (dataset; kinds image)
- Outputs: `out` (dataset)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `field` | string \| object {name} \| null | null | data | Vector field; field |
| `component_offset` | integer (≥0, ≤4093) | 0 | data |  |
| `direction_set` | "stk:cubic-26" \| "stk:cubic-100" \| "stk:cubic-110" \| "stk:cubic-111" \| "custom" | "stk:cubic-26" | data |  |
| `directions` | array of array[3] of number \| null | null | data | custom: directions |
| `numbering` | "stk" \| "stk-legacy" | "stk" | data |  |
| `min_magnitude` | number (≥0) | 0.1 | data |  |
| `max_angle_deg` | number (>0, ≤180) | 180.0 | data |  |
| `film_detection` | boolean | false | data |  |
| `film_epsilon` | number (≥0) | 1e-06 | data |  |
| `output` | string | "domain" | data |  |

## `stk.analysis.statistics@1` — Statistics

Per field and component: count, nan_count, min, max, mean, std (and magnitude).

- Inputs: `in` (dataset; kinds image, polydata, table)
- Outputs: `out` (table)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `fields` | array of string \| null | null | data |  |
| `components` | "each" \| "magnitude" \| "both" | "both" | data |  |

## `stk.render.axes@1` — Axes triad

Orientation triad overlay (axes_triad).

- Inputs: none
- Outputs: `layer` (layer)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `labels` | array[3] of string | ["x", "y", "z"] | client |  |
| `anchor` | "top_left" \| "top" \| "top_right" \| "left" \| "center" \| "right" \| "bottom_left" \| "bottom" \| "bottom_right" | "bottom_left" | client |  |
| `size_px` | integer (≥16, ≤512) | 80 | client |  |

## `stk.render.categorical_legend@1` — Categorical legend

Legend of category names and colours, from a categorical layer or a labels dataset.

- Inputs: `source` (layer | dataset; kinds labels)
- Outputs: `layer` (layer)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `field` | string \| null | null | data |  |
| `only_present` | boolean | true | data |  |
| `title` | string \| null | null | client |  |
| `anchor` | "top_left" \| "top" \| "top_right" \| "left" \| "center" \| "right" \| "bottom_left" \| "bottom" \| "bottom_right" | "right" | client |  |
| `columns` | integer (≥1, ≤8) | 1 | client |  |

## `stk.render.glyphs@1` — Glyphs

Instanced glyphs (arrow/cone/sphere/line/cube) at the input points, oriented by a vector field; scale and colour are client-side.

- Inputs: `in` (dataset; kinds polydata)
- Outputs: `layer` (layer)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `vectors` | string \| object {name} \| null | null | data | Direction field; field |
| `attributes` | "all" \| array of string | "all" | data |  |
| `shape` | "arrow" \| "cone" \| "sphere" \| "line" \| "cube" | "arrow" | client |  |
| `resolution` | integer (≥3, ≤64) | 8 | client |  |
| `center` | boolean | true | client |  |
| `scale` | object {by, field, factor} | {"by": "magnitude", "factor": "auto"} | client |  |
| `color` | object {by, solid, field, component, colormap, palette, range, range_mode, lightness_range} | {"by": "orientation"} | client |  |
| `opacity` | number (≥0, ≤1) | 1.0 | client |  |
| `name` | string \| null | null | client |  |

## `stk.render.orientation_legend@1` — Orientation legend

The stk:orientation-hsl colour sphere overlay (SimViz orientation legend).

- Inputs: none
- Outputs: `layer` (layer)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `title` | string \| null | null | client |  |
| `anchor` | "top_left" \| "top" \| "top_right" \| "left" \| "center" \| "right" \| "bottom_left" \| "bottom" \| "bottom_right" | "bottom_right" | client |  |
| `size_px` | integer (≥32, ≤512) | 120 | client |  |
| `lightness_range` | array[2] of number (≥0, ≤1) | [0.0, 1.0] | client |  |

## `stk.render.outline@1` — Outline

Bounding-box edges of the input as a lines layer.

- Inputs: `in` (dataset; kinds image, polydata)
- Outputs: `layer` (layer)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `color` | array[3] of number (≥0, ≤1) | [0.0, 0.0, 0.0] | client |  |
| `width_px` | number (≥0, ≤32) | 1.0 | client |  |
| `name` | string \| null | null | client |  |

## `stk.render.scalar_bar@1` — Scalar bar

Scalar bar overlay explaining the continuous colouring of the linked layer.

- Inputs: `source` (layer)
- Outputs: `layer` (layer)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `title` | string \| null | null | client | Title (null = field and unit) |
| `anchor` | "top_left" \| "top" \| "top_right" \| "left" \| "center" \| "right" \| "bottom_left" \| "bottom" \| "bottom_right" | "right" | client |  |
| `orientation` | "vertical" \| "horizontal" | "vertical" | client |  |
| `label_count` | integer (≥2, ≤20) | 5 | client |  |
| `format` | string | ".3g" | client |  |

## `stk.render.surface@1` — Surface

Polydata -> triangles (or lines/points) layer; a planar image (one axis of size 1) -> slice_image layer. Attributes travel raw; colouring is client-side.

- Inputs: `in` (dataset; kinds polydata, image)
- Outputs: `layer` (layer)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `attributes` | "all" \| array of string | "all" | data | Attributes to send |
| `color` | object {by, solid, field, component, colormap, palette, range, range_mode, lightness_range} | {"by": "solid", "solid": [0.8, 0.8, 0.8]} | client |  |
| `opacity` | number (≥0, ≤1) | 1.0 | client |  |
| `shading` | "smooth" \| "flat" | "smooth" | client |  |
| `edges` | boolean | false | client |  |
| `lighting` | boolean | true | client |  |
| `name` | string \| null | null | client |  |

## `stk.render.volume@1` — Volume

Dense volume texture with colour and opacity transfer functions (client-side).

- Inputs: `in` (dataset; kinds image)
- Outputs: `layer` (layer)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `field` | string \| object {name, component} \| null | null | data | field |
| `encoding` | "auto" \| "u8" \| "u16" \| "f32" | "auto" | data |  |
| `colormap` | string | "viridis" | client |  |
| `range` | [number \| null, number \| null] | [null, null] | client |  |
| `opacity` | array of [number (≥0, ≤1), number (≥0, ≤1)] | [[0.0, 0.0], [1.0, 0.8]] | client | Opacity points [x, alpha], x normalized over range |
| `sampling` | "linear" \| "nearest" | "linear" | client |  |
| `shade` | boolean | false | client |  |
| `name` | string \| null | null | client |  |

## `stk.view.camera@1` — Camera

A preset (fit to the scene bounds) or a numeric camera in physical coordinates.

- Inputs: none
- Outputs: `camera` (camera)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `preset` | "iso" \| "+x" \| "-x" \| "+y" \| "-y" \| "+z" \| "-z" \| null | "iso" | client |  |
| `position` | array[3] of number \| null | null | client |  |
| `focal_point` | array[3] of number \| null | null | client |  |
| `view_up` | array[3] of number \| null | null | client |  |
| `projection` | "perspective" \| "parallel" | "perspective" | client |  |
| `view_angle_deg` | number (>0) | 30.0 | client |  |
| `zoom` | number (>0) | 1.0 | client |  |
| `parallel_scale` | number (>0) \| null | null | client |  |

## `stk.view.scene@1` — Scene

Ordered layers plus the view (camera, viewport, background, lighting).

- Inputs: `layers` (layer; multi), `camera` (camera; optional)
- Outputs: `scene` (scene)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `background` | array[3] of number (≥0, ≤1) | [1.0, 1.0, 1.0] | client |  |
| `lighting` | "three_point" \| "headlight" \| "none" | "three_point" | client |  |
| `width` | integer (≥16, ≤16384) | 1600 | client |  |
| `height` | integer (≥16, ≤16384) | 1200 | client |  |
| `render_origin` | "auto" \| array[3] of number | "auto" | client |  |
| `title` | string \| null | null | client |  |

## `stk.output.dataset@1` — Dataset export

Write a dataset to VTKHDF (STK profile), VTI or NPY, or a table to CSV/JSON.

- Inputs: `in` (dataset)
- Outputs: `file` (file)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `format` | "vtkhdf" \| "vti" \| "npy" \| "csv" \| "json" | "vtkhdf" | data |  |
| `name` | string \| null | null | data | File stem (null = node id) |
| `fields` | array of string \| null | null | data |  |
| `precision` | "float64" \| "float32" | "float64" | data |  |

## `stk.output.image@1` — Image

Render a scene (offscreen VTK in a subprocess) or a plot (matplotlib) to PNG; plots also to SVG/PDF.

- Inputs: `source` (scene | plot)
- Outputs: `image` (image)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `width` | integer (≥16, ≤16384) \| null | null | client |  |
| `height` | integer (≥16, ≤16384) \| null | null | client |  |
| `magnification` | integer (≥1, ≤8) | 1 | client |  |
| `transparent` | boolean | false | client |  |
| `format` | "png" \| "svg" \| "pdf" | "png" | client |  |

## `stk.output.payload@1` — Render payload

Encode a scene as stk.payload/2 within the profile budget (optionally with a scene v1 downgrade).

- Inputs: `scene` (scene)
- Outputs: `payload` (payload)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `profile` | "auto" \| "phone" \| "web" \| "desktop" | "auto" | client |  |
| `budget` | null \| object {triangles, instances, points, voxels, bytes} | null | client |  |
| `v1_fallback` | boolean | false | client |  |

## `stk.plot.bar@1` — Bar chart

Bars of value columns per category row (e.g. label fractions).

- Inputs: `table` (table)
- Outputs: `plot` (plot)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `x` | string | **required** | data | Category column |
| `y` | array of string | **required** | data |  |
| `color_column` | string \| null | null | data | Column of '#rrggbb' colours |
| `orientation` | "vertical" \| "horizontal" | "vertical" | client |  |
| `log` | boolean | false | client |  |
| `title` | string \| null | null | client | Title |
| `size_in` | array[2] of number (>0, ≤100) | [6.0, 4.0] | client | Figure size (inches) |
| `dpi` | integer (≥30, ≤1200) | 200 | client |  |

## `stk.plot.heatmap@1` — Heatmap

2D slice of an image field as a heatmap (label fields use their categorical palette).

- Inputs: `in` (dataset; kinds image)
- Outputs: `plot` (plot)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `field` | string \| object {name, component} \| null | null | data | field |
| `axis` | "x" \| "y" \| "z" | "z" | data |  |
| `index` | integer (≥0) \| null | null | data |  |
| `colormap` | string | "viridis" | client |  |
| `range` | [number \| null, number \| null] | [null, null] | client |  |
| `aspect` | "equal" \| "auto" | "equal" | client |  |
| `colorbar` | boolean | true | client |  |
| `title` | string \| null | null | client | Title |
| `size_in` | array[2] of number (>0, ≤100) | [6.0, 4.0] | client | Figure size (inches) |
| `dpi` | integer (≥30, ≤1200) | 200 | client |  |

## `stk.plot.histogram@1` — Histogram

Histogram of a field (image/polydata) or a column (table).

- Inputs: `in` (dataset; kinds image, polydata, table)
- Outputs: `plot` (plot)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `field` | string \| object {name, component} \| null | null | data | field |
| `bins` | integer (≥1, ≤10000) | 64 | data |  |
| `range` | [number \| null, number \| null] | [null, null] | data |  |
| `density` | boolean | false | data |  |
| `log` | boolean | false | client |  |
| `color` | string | "C0" | client |  |
| `title` | string \| null | null | client | Title |
| `size_in` | array[2] of number (>0, ≤100) | [6.0, 4.0] | client | Figure size (inches) |
| `dpi` | integer (≥30, ≤1200) | 200 | client |  |

## `stk.plot.line@1` — Line plot

Columns against x with an optional second y axis (from 'table2' when linked), row filters and per-column styles (SimViz 1D page).

- Inputs: `table` (table), `table2` (table; optional)
- Outputs: `plot` (plot)

| param | type | default | stage | notes |
|---|---|---|---|---|
| `x` | string \| null | null | data | x column (null = index column) |
| `y` | array of string | **required** | data |  |
| `y2` | array of string | [] | data |  |
| `filters` | array of object {column, op, value} | [] | data |  |
| `stride` | integer (≥1) | 1 | data |  |
| `last_n` | integer (≥1) \| null | null | data |  |
| `x_label` | string \| null | null | client |  |
| `y_label` | string \| null | null | client |  |
| `y2_label` | string \| null | null | client |  |
| `x_scale` | "linear" \| "log" \| "symlog" | "linear" | client |  |
| `y_scale` | "linear" \| "log" \| "symlog" | "linear" | client |  |
| `y2_scale` | "linear" \| "log" \| "symlog" | "linear" | client |  |
| `styles` | object | {} | client |  |
| `legend` | boolean | true | client |  |
| `grid` | boolean | true | client |  |
| `stats` | boolean | false | client |  |
| `title` | string \| null | null | client | Title |
| `size_in` | array[2] of number (>0, ≤100) | [6.0, 4.0] | client | Figure size (inches) |
| `dpi` | integer (≥30, ≤1200) | 200 | client |  |
