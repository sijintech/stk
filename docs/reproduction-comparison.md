# Reproducible numerical comparison in a saved analysis

The [offline example](../examples/reproduction_comparison/README.md) connects the generic
comparison node to existing persistent analysis and report APIs. It is a software example
with manufactured data. Real paper reproduction, solver validation and scientific sensitivity
studies remain separate work.

The path uses existing contracts:

1. Write explicitly authored CSV inputs and a complete analysis definition. Select column
   names, source run status, units, tolerance, alignment and domain before running.
2. Register files with `p.files.index`, capture `p.snapshots.capture`, save the definition
   with `p.analyses.create`, and call `p.analysis_runs.prepare` with the original run UUID.
3. Explicitly call `p.analysis_runs.start`. The normal graph worker reads frozen copies,
   evaluates `stk.analysis.reproduction_compare@1` and renders plots. Preparation does not
   execute or inspect current input bytes in place of the frozen objects.
4. Read `p.analysis_runs.result`, which checks the archive against the saved run journal.
   Recompute each comparison with `suan.reproduction.verify`; also check independent
   analytic errors, ordered table values and actual plotted x/y arrays.
5. Explicitly create Report/1 from newly frozen evidence files. Review the actual
   `analysis_run` source, retain `sources_sha256`, then pass it to the create CAS.
6. Separately export the existing report. Verify the ZIP SHA/size, manifest, original
   report UUID and every selected asset. Reopen repeats verification without execution.

The example does not add a report source kind or alter Report/1, Report/2, Bridge or project
schemas. It uses the authenticated local project/run identity available through the existing
API, while caller-supplied scientific labels remain unauthenticated. SHA checks establish
integrity relative to the saved local evidence, not an author's signature or a physical claim.

The five cases deliberately include a tolerance failure, missing and failed rows, an explicitly
failed source run and incompatible units. Successful analysis execution means the software
delivered all requested outputs. Comparison status remains `failed` or `indeterminate` where
appropriate; no failed row is dropped and missing values are not replaced with zero.

The report keeps exact UTF-8 JSON in supported `*.json.txt` assets. `graph-result.json.txt`
contains the original archived manifest bytes with the journal's exact SHA. Individual
comparison documents are JSON serializations of their archived values, preserving JSON
number types and original inputs; `verify` recomputes both arithmetic and hashes. The report
also contains the real PNG bytes and `stk.plot-data/1` values from the worker's renderer.

The graph adapter's error output is a typed Table. Existing inline archive delivery preserves
column order, values and units but omits Field dtype/lossy descriptors. Its float columns are
display values, and missing floats use the existing `"NaN"` JSON marker. Exact original
numbers/markers and selected input Field descriptors remain in the comparison document.
Do not infer a stronger precision contract for exported tables or plots.

The example persists original analysis/run/report UUIDs and request notes before mutations.
Those notes are not backend edit-operation receipts. A lost prepare response is resolved by
querying the original UUID and comparing its complete request, document, input SHA/size and
record bindings. A read never retries prepare or creates a fake acknowledgement. A missing
original run remains `not_found`; inspect that outcome explicitly before deciding any later
action. A lost start reply similarly leads to observation of the original run.

Report creation and export are separate. After an uncertain create reply, readback uses the
original report UUID and the persisted request's exact source, snapshot, entry and asset
membership/record mapping. A valid ordinary metadata edit that removes or relabels evidence
is rejected as a different selection. Explicit export can proceed after a lost create reply or
an earlier export failure without recreating the report or changing its identity.

Constructing a session, opening a project, reading, recovering or verifying does not run the
analysis, renderer, solver or model. Headless service locks/cache/recent-project metadata may
still be written; this is not a zero-filesystem-write promise. Each CLI action uses private
temporary service/model-state/cache locations and never selects the visible desktop project,
configures the Viewer or changes layout. No model settings or network policy are modified.

Only explicit `start` dispatches one local analysis. Observation timeout stops observation;
closing its headless session cancels active local work. A new scientific or sensitivity run
requires an explicitly prepared new execution, rather than silently replaying an unknown
one. A complete real reproduction also requires permitted paper/data access, traceable
parameters and solver identity, valid units, independent reference data, justified tolerances
and sensitivity/convergence evidence. The manufactured example supplies none of those claims.
