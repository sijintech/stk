# Domain classifiers, label statistics and orientation colours (clean-room spec, v1)

> 中文摘要：本文档给出 STK 公开实现所用的铁电畴分类公式：26 个取向即 {−1,0,1}³ 的 26 个非零向量归一化，
> 附 STK 自有编号与兼容旧表的 `stk-legacy` 编号；以及幅值/角度阈值、薄膜检测、畴体积分数、HSL 取向色图与分类调色板。
> 本规范为净室（clean-room）文本：实现者只能依据本文档编码，不得查阅 muprosdk 源码；VO2 分类器不在公开 STK 中。

Status: frozen for Milestone 1 (Phase A). Implemented by `suan/analysis/{orientation,labels,palettes}.py`
(NumPy only) and exposed through the graph nodes `stk.analysis.orientation_classify@1`,
`stk.analysis.film_detect@1`, `stk.analysis.label_fractions@1` and `stk.filter.label_surfaces@1`
(see `stk-graph-v1.md`).

## 0. Clean-room rules

- Everything here is either a definition (the 26 directions are the normalized nonzero vectors of
  {−1, 0, 1}³), a textbook operation (argmax of cosines, HSL colour conversion, counting, marching
  cubes), or behaviour of SimViz as documented in STK's planning notes and in STK's own MIT file
  `toolkits/sviz/nt_vtk.py`.
- Implementers **must not** open `muprosdk/tools/mupro_viz/**` or any other muprosdk source. Tests are
  built from physics (known directions, constructed films), never from `mupro_viz` output.
- `toolkits/sviz/nt_vtk.py` is used **only** by cross-check tests of the `stk-legacy` numbering and
  palette. Do not copy it: its direction table has a typo (row 21 sets `domainOrth[22][2]` instead of
  `[21][2]`, harmless because the array starts zeroed), and its provenance ("nibiru-tech") is still an
  open owner question.
- The VO2 M1/M2 classifier, MuPRO's exact thresholds and label maps are **not** part of public STK.
  They belong to the private `stk-mupro` package, which can register `mupro.*` nodes through the
  `stk.nodes` entry point.

## 1. Label conventions

A classification result is an integer **label field** (`tensor: "label"`, `components: 1`, dtype
`int16`) with `categories` (field-1). Reserved values, identical in both numberings:

| value | meaning | produced by |
|---|---|---|
| `-1` | unclassified or no data: magnitude ≤ `min_magnitude`, best angle ≥ `max_angle_deg`, a non-finite component, or air above a film | classifier, film detection |
| `0` | substrate | film detection only |
| `1..N` | variant `k` of the active direction set and numbering | classifier |

Every category entry carries `value`, `name`, and for variants also `direction` (unit vector),
`family` (`"T"`, `"O"`, `"R"`, or absent for custom sets), `aliases` and `color` (from the default
palette of the numbering, §6). The field's `quantity` is `domain_variant`, `unit` is `"1"` and
`palette` is `stk:cubic-26-orientation` (numbering `stk`, including the subsets of §2.4),
`stk-legacy:ferro27` (numbering `stk-legacy`) or `stk:categorical` (custom sets).

Renderers never interpolate labels: slices use nearest sampling and surfaces are built per label (§7).

## 2. Direction sets

The **cubic-26 set** is the 26 vectors v ∈ {−1, 0, 1}³ \ {0}, each normalized to unit length
d = v / |v|. Families by the number of nonzero components n(v):

| family | n(v) | directions | name |
|---|---|---|---|
| `T` | 1 | 6 ⟨100⟩ | tetragonal |
| `O` | 2 | 12 ⟨110⟩ | orthorhombic |
| `R` | 3 | 8 ⟨111⟩ | rhombohedral |

Set ids: `stk:cubic-26` (all), `stk:cubic-100` (T), `stk:cubic-110` (O), `stk:cubic-111` (R), and
`custom` (a user list of nonzero 3-vectors, normalized; a zero vector is an error
`invalid_direction`).

### 2.1 STK numbering (`numbering: "stk"`, the default)

Generated, no table needed:

1. Enumerate `itertools.product((1, 0, -1), repeat=3)` (lexicographic, +1 before 0 before −1).
2. Keep the **representatives**: nonzero vectors whose first nonzero component is +1 (13 vectors).
3. Stable-sort the representatives by n(v) (1, then 2, then 3).
4. Emit each representative followed immediately by its negation. Labels are 1-based.

So antiparallel variants are consecutive (odd label = representative, even label = its negation),
and the families occupy T 1–6, O 7–18, R 19–26.

**STK names** are the family letter plus Miller-style brackets with `-` for negative components,
e.g. `T[100]`, `O[1-10]`, `R[-1-1-1]`. Aliases list the legacy name (`R1+(+,+,+)`), its short form
(`R1+`) and, for T variants, the nt_vtk short names `a1+ a1- a2+ a2- c+ c-`.

### 2.2 Legacy numbering (`numbering: "stk-legacy"`)

Reproduces the table STK already publishes under MIT in `toolkits/sviz/nt_vtk.py` (and SimViz's
label names): R 1–8, O 9–20, T 21–26, each pair `+` then `−`. Only defined for `stk:cubic-26`;
any other set with `stk-legacy` is an error `numbering_unsupported`. Legacy names are
`<family><n><sign>(<signs>)`, e.g. `R1+(+,+,+)`, `T3-(0,0,-)`; aliases carry the STK name.

### 2.3 Full table

Colours are the `stk:cubic-26-orientation` palette (§6.3), rounded to 4 decimals.

| STK label | vector | family | STK name | legacy label | legacy name | colour (RGB, `stk:cubic-26-orientation`) |
|---|---|---|---|---|---|---|
| 1 | (+1, 0, 0) | T | `T[100]` | 21 | `T1+(+,0,0)` | 1.0000, 0.0000, 0.0000 |
| 2 | (-1, 0, 0) | T | `T[-100]` | 22 | `T1-(-,0,0)` | 0.0000, 1.0000, 1.0000 |
| 3 | (0, +1, 0) | T | `T[010]` | 23 | `T2+(0,+,0)` | 0.5000, 1.0000, 0.0000 |
| 4 | (0, -1, 0) | T | `T[0-10]` | 24 | `T2-(0,-,0)` | 0.5000, 0.0000, 1.0000 |
| 5 | (0, 0, +1) | T | `T[001]` | 25 | `T3+(0,0,+)` | 0.8000, 0.8000, 0.8000 |
| 6 | (0, 0, -1) | T | `T[00-1]` | 26 | `T3-(0,0,-)` | 0.2000, 0.2000, 0.2000 |
| 7 | (+1, +1, 0) | O | `O[110]` | 9 | `O1+(+,+,0)` | 1.0000, 0.7500, 0.0000 |
| 8 | (-1, -1, 0) | O | `O[-1-10]` | 10 | `O1-(-,-,0)` | 0.0000, 0.2500, 1.0000 |
| 9 | (+1, 0, +1) | O | `O[101]` | 13 | `O3+(+,0,+)` | 1.0000, 0.4243, 0.4243 |
| 10 | (-1, 0, -1) | O | `O[-10-1]` | 14 | `O3-(-,0,-)` | 0.0000, 0.5757, 0.5757 |
| 11 | (+1, 0, -1) | O | `O[10-1]` | 15 | `O4+(+,0,-)` | 0.5757, 0.0000, 0.0000 |
| 12 | (-1, 0, +1) | O | `O[-101]` | 16 | `O4-(-,0,+)` | 0.4243, 1.0000, 1.0000 |
| 13 | (+1, -1, 0) | O | `O[1-10]` | 11 | `O2+(+,-,0)` | 1.0000, 0.0000, 0.7500 |
| 14 | (-1, +1, 0) | O | `O[-110]` | 12 | `O2-(-,+,0)` | 0.0000, 1.0000, 0.2500 |
| 15 | (0, +1, +1) | O | `O[011]` | 17 | `O5+(0,+,+)` | 0.7121, 1.0000, 0.4243 |
| 16 | (0, -1, -1) | O | `O[0-1-1]` | 18 | `O5-(0,-,-)` | 0.2879, 0.0000, 0.5757 |
| 17 | (0, +1, -1) | O | `O[01-1]` | 19 | `O6+(0,+,-)` | 0.2879, 0.5757, 0.0000 |
| 18 | (0, -1, +1) | O | `O[0-11]` | 20 | `O6-(0,-,+)` | 0.7121, 0.4243, 1.0000 |
| 19 | (+1, +1, +1) | R | `R[111]` | 1 | `R1+(+,+,+)` | 1.0000, 0.8366, 0.3464 |
| 20 | (-1, -1, -1) | R | `R[-1-1-1]` | 2 | `R1-(-,-,-)` | 0.0000, 0.1634, 0.6536 |
| 21 | (+1, +1, -1) | R | `R[11-1]` | 6 | `R3-(+,+,-)` | 0.6536, 0.4902, 0.0000 |
| 22 | (-1, -1, +1) | R | `R[-1-11]` | 5 | `R3+(-,-,+)` | 0.3464, 0.5098, 1.0000 |
| 23 | (+1, -1, +1) | R | `R[1-11]` | 7 | `R4+(+,-,+)` | 1.0000, 0.3464, 0.8366 |
| 24 | (-1, +1, -1) | R | `R[-11-1]` | 8 | `R4-(-,+,-)` | 0.0000, 0.6536, 0.1634 |
| 25 | (+1, -1, -1) | R | `R[1-1-1]` | 4 | `R2-(+,-,-)` | 0.6536, 0.0000, 0.4902 |
| 26 | (-1, +1, +1) | R | `R[-111]` | 3 | `R2+(-,+,+)` | 0.3464, 1.0000, 0.5098 |

Legacy order (label → vector) for reference: 1 (+,+,+), 2 (−,−,−), 3 (−,+,+), 4 (+,−,−),
5 (−,−,+), 6 (+,+,−), 7 (+,−,+), 8 (−,+,−), 9 (+,+,0), 10 (−,−,0), 11 (+,−,0), 12 (−,+,0),
13 (+,0,+), 14 (−,0,−), 15 (+,0,−), 16 (−,0,+), 17 (0,+,+), 18 (0,−,−), 19 (0,+,−), 20 (0,−,+),
21 (+,0,0), 22 (−,0,0), 23 (0,+,0), 24 (0,−,0), 25 (0,0,+), 26 (0,0,−).

### 2.4 Subsets and custom sets

- `stk:cubic-100|110|111` keep the STK order restricted to the family and relabel 1..n
  (cubic-100 = STK 1–6; cubic-110 = STK 7–18 minus 6; cubic-111 = STK 19–26 minus 18). Names and
  directions are unchanged; the palette entries use the colour of the direction (§6.3).
- `custom`: labels 1..n in the order given; names `d1`..`dn`; no family; colours from
  `stk:categorical` (§6.5).

## 3. Classification (`stk.analysis.orientation_classify@1`)

Parameters: `field` (vector field, ≥ 3 components; `null` = first field with ≥ 3 components),
`component_offset` o (use components o, o+1, o+2; e.g. 3 for the second triplet of a 6-column DAT),
`direction_set`, `directions` (custom), `numbering`, `min_magnitude` (≥ 0, default 0.1),
`max_angle_deg` (0 < a ≤ 180, default 180), `film_detection` (default false), `film_epsilon`
(default 1e-6), `output` (field name, default `domain`).

For every point with vector p = (p_o, p_{o+1}, p_{o+2}) in float64:

1. If any component is non-finite → **−1**.
2. m = ‖p‖₂. If m ≤ `min_magnitude` → **−1** (strict: classified only when m > threshold).
3. For the unit directions d_1..d_N **in the order of the active numbering**, c_k = (p · d_k) / m.
4. k* = the **first** index of the maximum c_k (ties go to the lower label of the active numbering;
   this reproduces nt_vtk's first-minimum-angle rule for `stk-legacy`).
5. If `max_angle_deg` = 180 the point is accepted. Otherwise it is accepted iff
   c_{k*} > cos(`max_angle_deg` · π / 180) (strict; equivalently angle < max_angle).
6. Label = k* (1-based) if accepted, else **−1**.
7. If `film_detection` is true, apply §4 afterwards: layers at or below `substrate_top` become **0**,
   layers above `film_top` become **−1**; film layers keep their labels. The film info (§4) is stored
   in the output dataset's `attrs["film"]`.

The output dataset is the input plus the label field (input fields are kept, zero-copy). Vectorize
as an (n_points × N) matrix product in chunks of about 10⁶ points (target ≤ 1 s for 128³ on the
r730xd). The default threshold 0.1 is STK's choice (nt_vtk uses 0.1 as function default and 0.05 as
object default; SimViz 0.3/0.5); presets always set `min_magnitude` explicitly, and reports must
state it together with the field's unit.

## 4. Film detection (`stk.analysis.film_detect@1` and `film_detection: true`)

Detects a film on a substrate with air (or vacuum) above it, along **z** (grid index k; with the
`(z, y, x, c)` layout a layer is `array[k]`).

- s_k = max over the layer of |p_x| + |p_y| + |p_z| (L1 norm of the selected triplet), ignoring
  non-finite values. Layer k is **polarized** iff s_k > ε (`epsilon`, default 1e-6).
- No polarized layer → `detected: false`; no label changes; all indices in the info are `null`.
- `film_bottom` = lowest polarized k; `film_top` = highest polarized k;
  `substrate_top` = `film_bottom` − 1 (−1 when there is no substrate layer).
- `film_detect` adds an int8 label field (`output`, default `film`) with categories
  `-1 "air"`, `0 "substrate"`, `1 "film"`: k ≤ `substrate_top` → 0, `film_bottom` ≤ k ≤ `film_top`
  → 1 (unpolarized layers inside the film stay film), k > `film_top` → −1.
- `info` (value output, and `attrs["film"]` when used inside the classifier):
  `{"detected": bool, "axis": "z", "epsilon": ε, "substrate_top": int|null, "film_bottom": int|null,
  "film_top": int|null, "substrate_layers": int, "film_layers": int, "air_layers": int}`.

SimViz also wrote a −1 ghost border around the classified grid (dimensions + 3). STK never changes
the grid; `stk.filter.label_surfaces@1` pads internally when `close_boundaries` is true (§7).

## 5. Label fractions (`stk.analysis.label_fractions@1`)

Input: a labels dataset and its label field (`field`, `null` = first label field). Point fields count
points; cell fields count cells (on uniform grids counts are volume fractions).

- count(v) = number of samples with value v, for every category value v and every value present.
- Denominator N = Σ count(v) over values **not** in `exclude` (default `[-1, 0]`).
- fraction(v) = count(v) / N for v ∉ exclude; for excluded values the row's fraction is `NaN`.
  If N = 0 all fractions are `NaN` and the node warns `empty_denominator`.
- Values present in the data but missing from `categories` get a row named `unknown(<v>)` and a
  warning `unknown_label`.
- `include_empty` (default true) keeps rows with count 0 for every category.

`out` table columns (in this order): `value` int64 (role `label`), `name` string, `family` string
(`""` if none), `count` int64, `fraction` float64 (unit `"1"`), `color` string `#rrggbb` (from the
category colour; `""` if none). Rows are sorted by value.
`families` table: `family` string, `count` int64, `fraction` float64 — one row per family in order of
first appearance in `categories`, summing the non-excluded rows; categories without a family are
left out. Both tables carry `attrs = {"field", "denominator": N, "total": total samples,
"excluded": {"-1": n, "0": n, ...}}`.

## 6. Colours

Colours are display aids, never measurements (numbers come from probing the data).

### 6.1 HSL → RGB (CSS Color 4)

Inputs h ∈ [0, 360) degrees, s, l ∈ [0, 1]:

```
C  = (1 − |2l − 1|) · s
H' = (h mod 360) / 60
X  = C · (1 − |(H' mod 2) − 1|)
(r1, g1, b1) = (C,X,0) if H'∈[0,1); (X,C,0) [1,2); (0,C,X) [2,3); (0,X,C) [3,4); (X,0,C) [4,5); (C,0,X) [5,6)
m0 = l − C/2
RGB = (r1 + m0, g1 + m0, b1 + m0)
```

8-bit values are `floor(255 · c + 0.5)`.

### 6.2 `stk:orientation-hsl` (continuous, by direction)

For a vector p, the maximum magnitude M > 0 of the layer (payload `color.max_magnitude`) and a
lightness range [l0, l1] (default [0, 1], SimViz-compatible):

- m = ‖p‖, m_xy = √(p_x² + p_y²).
- If M ≤ 0 or m = 0: grey, s = 0, l = l0 + (l1 − l0)/2.
- Else if m_xy < 10⁻⁵ · M: grey, s = 0, l = l0 + (l1 − l0) · clamp((p_z + M) / (2M), 0, 1).
- Else: h = atan2(p_y, p_x) in degrees mod 360; s = min(m / M, 1);
  l = l0 + (l1 − l0) · (p_z / m + 1) / 2.

(SimViz used an absolute 10⁻⁵ for the in-plane test; STK makes it relative to M.)

Reference values ([l0, l1] = [0, 1]):

| p | M | RGB | RGB8 |
|---|---|---|---|
| (1, 0, 0) | 1 | 1, 0, 0 | 255, 0, 0 |
| (0, 1, 0) | 1 | 0.5, 1, 0 | 128, 255, 0 |
| (−1, 0, 0) | 1 | 0, 1, 1 | 0, 255, 255 |
| (0, −1, 0) | 1 | 0.5, 0, 1 | 128, 0, 255 |
| (0, 0, 1) | 1 | 1, 1, 1 | 255, 255, 255 |
| (0, 0, −1) | 1 | 0, 0, 0 | 0, 0, 0 |
| (0.5, 0, 0) | 1 | 0.75, 0.25, 0.25 | 191, 64, 64 |
| (1, 0, 1) | √2 | 1, 0.707107, 0.707107 | 255, 180, 180 |
| (1, 1, 1) | √3 | 1, 0.894338, 0.57735 | 255, 228, 147 |
| (0, 0, 0) | 1 | 0.5, 0.5, 0.5 | 128, 128, 128 |

Web, offscreen VTK and Blender implement this function identically (it is the only function
colormap in payload v2); the orientation legend sphere (overlay `orientation_legend`) colours each
surface point n of a unit sphere with `stk:orientation-hsl(n, M = 1)`.

### 6.3 `stk:cubic-26-orientation` (categorical, numbering `stk`)

Variant v with unit direction d gets `stk:orientation-hsl(d, M = 1, [l0, l1] = [0.2, 0.8])`
(compressed lightness so ±z variants are light/dark grey instead of white/black; hues match the
glyph colours). Reserved: `-1` → (1, 1, 1) "unclassified", `0` → (0.75, 0.75, 0.75) "substrate".
The values are in §2.3. Subsets use the same colours for the same directions.

### 6.4 `stk-legacy:ferro27` (categorical, numbering `stk-legacy`)

The 27-entry palette already published in STK under MIT (`toolkits/sviz/nt_vtk.py` `domainRGB`,
`toolkits/sviz/mupro_domain.json`), indexed by legacy label; `-1` → (1, 1, 1). Implementations keep
these values in `suan/analysis/palettes.py` and cross-check them against the two files in a test.
Its origin is an open owner question (see §0); the default numbering does not depend on it.

| legacy label | RGB | legacy label | RGB |
|---|---|---|---|
| 0 (substrate) | 0.752912, 0.752912, 0.752912 | 14 | 0.678201, 0.498270, 0.301423 |
| 1 | 0, 0, 1 | 15 | 0.476371, 0.035432, 0.14173 |
| 2 | 0.46, 0.7175, 0.8135 | 16 | 0.961169, 0.251965, 0.199862 |
| 3 | 0, 0.153787, 0 | 17 | 0.355309, 0.968874, 0.355309 |
| 4 | 0, 1, 0 | 18 | 0.038446, 0.646290, 0.038446 |
| 5 | 1, 0, 0 | 19 | 0.766921, 0.766921, 0.766921 |
| 6 | 1, 0.566921, 0.633741 | 20 | 0.169550, 0.169550, 0.169550 |
| 7 | 1, 0.418685, 0 | 21 | 0.566921, 0.566921, 0.566921 |
| 8 | 1, 1, 0 | 22 | 0.393695, 0.015747, 0.885813 |
| 9 | 1, 0, 1 | 23 | 0, 0, 0 |
| 10 | 0.64629, 0.130165, 0.130165 | 24 | 1, 0.710881, 0 |
| 11 | 0.9, 0.566921, 0.633741 | 25 | 0.885813, 0.813533, 0.301423 |
| 12 | 0.751111, 0.393695, 0.751111 | 26 | 0.8867188, 0.4335937, 0.0273438 |
| 13 | 0.418685, 0.027128, 0.027128 | | |

### 6.5 `stk:categorical` (generic label fields)

For label value v ≥ 1, i = v − 1: h = (i · 137.50776405003785) mod 360 (golden angle), s = 0.65,
l = [0.50, 0.38, 0.62][i mod 3]. Reserved: 0 → (0.75, 0.75, 0.75), −1 → (1, 1, 1), v < −1 →
(0.5, 0.5, 0.5). First values: 1 → (0.825, 0.175, 0.175), 2 → (0.133, 0.627, 0.2771),
3 → (0.6613, 0.373, 0.867), 4 → (0.825, 0.744, 0.175).

A field's `categories[].color`, when present, always wins over its palette.

## 7. Label surfaces (`stk.filter.label_surfaces@1`)

For each label v in the requested set (`labels: "present"` = values present in the field, minus
`exclude`, default `[-1, 0]`; or an explicit list):

1. Indicator I_v = 1.0 where label = v else 0.0 (float32, point data, same grid).
2. If `close_boundaries` (default true): pad I_v with one layer of 0 on every side (dimensions + 2,
   origin − spacing) so every surface is closed at the box boundary.
3. Contour I_v at 0.5 (marching cubes / flying edges; `vtkFlyingEdges3D` exists from VTK 9.3).
4. Smoothing (`smoothing`, default `windowed_sinc`): windowed-sinc with `smooth_iterations`
   (default 30) and pass band `smooth_factor` (default 0.1), boundary and feature-edge smoothing off,
   coordinates normalized; or `laplacian` with relaxation factor `smooth_factor` (SimViz used
   Laplacian, 30 iterations, 0.1); or `none`.
5. Clamp the vertices into the dataset's bounds (per axis `[0, (n − 1)·spacing]` in grid
   coordinates; axes of one sample keep their slab): the closing faces that the padding put half a
   cell outside the grid (and smoothing may push further) are projected onto the bounding box, so
   surfaces never overhang the grid or its outline, picks on them land inside the grid, and the
   surface stays closed and outward oriented.
6. Normals if `compute_normals` (consistent orientation, no splitting).
7. Cell field `label` = v (int32) with the input field's categories and palette.

The per-label surfaces are appended into one polydata (triangles). Where two labels touch, two
coincident faces are drawn (as in SimViz); a later `method: discrete` may remove them. Target: 26
labels on 128³ in ≤ 4 s.

## 8. Tests from physics (guidance for Phase B)

- Each of the 26 unit directions (and 0.7 × it) is labelled with its own label in both numberings;
  the STK↔legacy mapping equals §2.3.
- A 10° perturbation keeps the label; a vector 30° from every direction with `max_angle_deg = 20`
  gives −1; magnitudes at or below `min_magnitude` give −1; NaN gives −1; an exact tie picks the
  lower label of the active numbering.
- Film: a constructed stack (substrate zeros, a polarized film, air zeros) gives the expected
  indices and labels; `toolkits/sviz/test/PELOOP.00001000.dat` (64×1×150, 6 columns,
  `component_offset` 3) gives fractions that sum to 1 over non-excluded labels.
- Palettes: `stk-legacy:ferro27` equals nt_vtk `domainRGB` and `mupro_domain.json`; the legacy
  numbering equals nt_vtk's `domainOrth` rows 1–26 (reading row 21 as (1, 0, 0)).
- Orientation colours equal the table in §6.2.
