# Explicit reproduction comparisons (`stk.reproduction-comparison/1`)

This additive numerical core compares caller-supplied scalar or curve evidence.
It performs no file, network, model, solver, project or registry operation. It does
not authenticate a paper, approve an assumption, establish a real solver run, or
judge a paper's scientific quality. Existing report/1, report/2, graph, Bridge and
project contracts remain unchanged. Integration with those contracts is pending.

The public standard-library-only API is `suan.reproduction.compare(plan)` and
`verify(document)`. Invalid inputs raise `ComparisonError` with a bounded message
and a `code`; no partial result is returned. Numerically valid but unavailable,
failed, incompatible or insufficient evidence produces an `indeterminate` result.

## Frozen input

A plan has exactly these keys:

```json
{
  "format": "stk.reproduction-comparison-plan/1",
  "kind": "scalar",
  "reference": {"status": "succeeded", "unit": "K", "value": 10, "source": {}},
  "actual": {"status": "succeeded", "unit": "K", "value": 11, "source": {}},
  "tolerance": {"absolute": 0.5, "relative": 0.1},
  "rule": {"criterion": "absolute_plus_relative"}
}
```

`kind` is `scalar` or `curve`. Each side has a caller-supplied run status:
`succeeded`, `failed` or `missing`. These labels are observations supplied by the
caller, not authenticated lifecycle receipts. A failed/missing run cannot pass
because some retained numeric values happen to agree. Values are finite JSON
numbers, excluding booleans; null retains a missing measurement. Non-finite,
non-numeric and out-of-binary64-range input values are input errors. Integers and
floats, including original negative zero, remain in the detached frozen plan.

`source` is a bounded JSON object preserved without interpretation. DOI strings,
locators, hashes or `approved` labels inside it do not establish source validity,
authorization or reviewer identity. A later integration must independently bind
actual article/version/span evidence, approvals, frozen workflow/input identity,
program and output bytes. Missing paper parameters and explicit assumptions can
be recorded in these objects, but this numerical core does not infer completeness
or approve their scientific sufficiency.

Unit labels are explicit strings of at most 128 characters, or null. Both sides
must have identical known labels. No conversion, trimming-based equivalence or
inferred dimensional relation is performed: `s` and `ms` mismatch. Null, blank,
`unknown`, `unspecified`, `normalized` and `none` (case-insensitive after trimming
for unknown detection only) are unavailable units. A bare `normalized` label lacks
a shared normalization definition. A caller may supply an explicit definition-bound
label, but the core still cannot authenticate that definition. `1` explicitly
identifies dimensionless values.

## Scalar criterion

Absolute and relative tolerances are required finite nonnegative numbers in the
reference value's unit and dimensionless units, respectively. The per-point rule is:

```text
signed_error = actual - reference
absolute_error = abs(signed_error)
allowed_error = absolute + relative * abs(reference)
passed iff absolute_error <= allowed_error
```

The comparison is inclusive at the boundary. Relative error uses the reference
magnitude, including for negative reference values. A zero reference contributes
zero relative allowance; an absolute allowance is necessary for nonzero error.
Tolerances are never selected from observed results.

## Curve criterion and alignment

For curves each side instead has exactly
`{status, x_unit, y_unit, points, source}`. `points` is an ordered list of at most
4096 objects `{x,y,status}`. A point status is `ok`, `failed` or `missing`. Finite
known x coordinates must be strictly increasing without duplicates. No sorting,
deduplication, smoothing, unit conversion or implicit resampling occurs. Null x
or y values remain visible as unavailable evidence.

The rule has exactly:

```json
{
  "criterion": "all_reference_points_and_full_domain",
  "alignment": "linear",
  "domain": [0, 2],
  "extrapolation": "forbid"
}
```

`domain` is an explicit finite closed interval with minimum <= maximum; equal
endpoints define a single-sample comparison. Both reference and actual coordinate
spans must cover the entire requested interval. Missing either boundary cannot
silently turn a partial overlap into a successful whole-domain comparison.
Out-of-domain points remain in the frozen plan and do not affect this explicit
subdomain's numerical verdict. Unknown point positions block a full-domain verdict
because their membership in the requested domain cannot be determined.

Every reference point within the domain is compared. Reference points with unknown
positions are also retained as indeterminate result points. `alignment="exact"`
requires the same actual x; it never interpolates. `alignment="linear"` first uses
an exact actual point, otherwise interpolates only between its two immediate
neighbors in the original actual series. Both neighbors must have status `ok` and
known y values. Interpolation cannot cross an intervening failed/missing sample.
Extrapolation is always forbidden, including when the requested domain is only
partially covered. Other alignment, criterion or extrapolation values are errors.

A failed/missing actual point inside the requested domain blocks a complete
whole-domain pass even if the reference grid did not sample that exact x. Failed
or missing samples are preserved in the plan rather than dropped before scoring.
The criterion proves agreement at the declared reference samples and availability
across the requested span; it does not prove equality between sampled locations
or establish physical convergence.

## Arithmetic, outcomes and metrics

Intermediates use exact rational arithmetic over each submitted number's Python
JSON-style decimal spelling, including piecewise-linear interpolation and the
tolerance boundary. This avoids overflowing an intermediate slope, difference or
square before a finite answer can be obtained. Result point values/errors are
binary64 floats. If an interpolated value, error or tolerance cannot be represented
as a finite nonzero binary64 value when mathematically nonzero, the point is
`indeterminate` with `numeric_out_of_range`; infinity or a silently underflowed
zero is not published. The original input values remain frozen.

Each point includes its original reference index/x/value, actual value, actual
source indices (one exact point or two interpolation neighbors), signed/absolute
error, allowed error, outcome and reason. Indeterminate error fields are null.

Metrics include the reference samples in the explicit domain plus unknown-position
reference samples, compared samples, sample coverage, passed/failed/indeterminate
counts, maximum absolute error and RMSE. `compared_samples` includes only points
with a numeric passed/failed verdict. `coverage` is that count divided by the
reported reference sample count (zero for no samples); it is **not** domain
coverage or scientific confidence. Maximum error and RMSE summarize compared
samples only and are null if none can be compared. RMSE scales errors before
squaring to avoid overflow; its output has ordinary binary64 rounding.

The result is `passed` only when all required samples pass, at least one sample
exists, both domains are covered and no unavailable evidence remains. Complete
numeric evidence exceeding tolerance is `failed`. Any unavailable requirement
makes the overall result `indeterminate`, even when some retained individual
points are numerically failed. Those failures and partial metrics remain visible;
an indeterminate result never hides them or becomes a pass.

Reasons include unavailable run/value/point status, unknown/mismatched units,
missing point positions, incomplete reference/actual domain, absent exact samples,
forbidden extrapolation, absent reference samples and numeric output range.
Malformed shapes, unsupported rules, non-finite input, duplicate/descending x,
invalid tolerances and budget violations raise input errors instead.

## Identity, reopen and resource limits

The returned document has exactly
`{format,plan,plan_sha256,result,result_sha256}`. `plan` is detached from caller
mutation. Canonical encoding is UTF-8 JSON with sorted object keys, no whitespace,
`ensure_ascii=False`, and non-finite numbers forbidden. Array order and numeric
types are preserved. `plan_sha256` hashes that canonical plan. `result_sha256`
hashes canonical `{format,plan_sha256,result}`.

`verify(document)` recomputes comparison from the frozen plan and compares the
whole document, rather than trusting matching outer hashes alone. It returns True
or raises `comparison_mismatch` (or the applicable input error). Hashes prove
internal consistency only. Replacing a plan and honestly recomputing its result is
a new comparison, not authentication of any external evidence or original author.

Inputs and returned/reopened documents are limited to 2 MiB each, depth 12 and
300000 JSON nodes, in addition to 4096 points per curve and bounded numeric inputs.
All combined budgets apply; oversize results fail instead of publishing a document
that cannot be reopened. Strings must be valid UTF-8; unsupported Python objects
and cyclic/deep containers fail closed. No package import or comparison launches
workers, performs downloads, changes model/network settings, or executes a solver.

This contract does not complete S6. Real licensed MuPRO article selection,
independent review of settings/reference data, authenticated runtime/output
binding, sensitivity runs, native UI and source-bearing report integration remain
required. The pending electric-field-scan choice, proposal persistence choice and
S2c execution powers are unchanged; PET work remains deferred.

## Additive graph adapter

`stk.analysis.reproduction_compare@1`, implementation version 1, is an analysis
node with two required `table` inputs, `reference` and `actual`. It returns
`comparison` (`value<json>`, the complete core document above) and `errors` (`table`).
The deterministic outputs may use the existing graph disk cache. No graph or
project operation prepares or runs a solver as part of this node.

Required parameters have no defaults: `kind` (`scalar|curve`),
`reference_value`/`actual_value` (explicit column names),
`reference_status`/`actual_status` (`succeeded|failed|missing`), nonnegative
`absolute`/`relative`, and `alignment` (`exact|linear`). Missing run statuses or
tolerances are graph validation errors; the node never infers successful execution.
Column names are 1–128 characters. Nullable parameters default to null:
`reference_x`/`actual_x`, `reference_row_status`/`actual_row_status`, and `domain`
(null or a two-number interval). Curves require explicit x columns and domain.
Scalar comparison requires exactly one row, or zero rows only for an explicitly
failed/missing source, and requires `alignment=exact`, `domain=null`, with no x
or row-status columns: scalar evidence is not resampled. Required alignment makes
that scalar restriction explicit rather than applying a curve interpolation default.

Selected value/x fields must be complete numeric scalar row arrays; optional curve
row-status fields must be strings `ok|failed|missing`. Each input has at most 4096
rows. Units come directly from selected field descriptors, without an override or
conversion parameter. Known labels are still only supplied metadata, not proof of
the physical units of an upstream solver. NaN is explicitly normalized to a missing
coordinate/value for the core; its original `"NaN"` marker remains frozen. Infinite
values are input errors, not observations to filter out. No row is removed before
comparison. Unknown locations and failed/missing curve rows keep the core's
indeterminate and no-interpolation semantics.

Each core `source` freezes the input Table ID, explicit value/x/status selection,
selected field descriptors/dtypes,
all original selected-column values, original provenance/attrs and explicit run
status. The metadata is marked `authority="unverified"`; it does not establish
an authenticated run, article, approval or reviewer. Non-finite original markers
use `"NaN"`, `"Inf"`, `"-Inf"`; unsupported/deep/oversize metadata fails with a bounded
node error instead of silently dropping provenance. Core combined byte/depth/node
budgets apply in addition to the row limit. Upstream arrays and metadata are not
modified. Unselected columns are outside this comparison evidence selection.

The error Table has `reference_index` (int64/index), `x`, `reference`, `actual`,
`signed_error`, `absolute_error`, `allowed_error` (float64), `status`, `reason`,
`actual_indices`, `x_exact`, `reference_exact`, `actual_exact` (strings). Missing
numeric output is NaN for the Table, and null in the JSON document; reason/status
columns remain available. x/reference/actual use their respective source units;
error/tolerance columns use reference y units, and no errors are computed when
units differ. Scalar x is unavailable, with unit `unspecified`.

The three `*_exact` columns preserve JSON original values independently of the
float plotting columns. For linearly interpolated actual values, `actual_exact`
instead contains `{alignment:"linear",reference_x,points:[left,right]}` with the
original endpoint objects, allowing exact reconstruction from the declared rule.
Numeric plotting fields set their descriptor's `lossy` flag if conversion changes
an original integer or interpolation rounds an exact rational value. Known upstream
precision-loss flags also propagate to dependent value/error columns. Full original
column values and dtypes also remain in the core plan. Table attrs carry the plan
and result hashes and comparison status, without duplicating the full document.

The canonical catalog declaration and generated node table are in
`docs/specs/catalog/m1_nodes.py`, `stk-catalog-m1.json` and `stk-graph-v1.md`.
Future numerical or adapter semantic changes must review the core contract and
increment this node's implementation version, so old graph cache entries cannot
masquerade as new results. This adapter adds no report/1 or report/2 source kind,
Bridge method, project format, agent execution permission, or scientific validation.
