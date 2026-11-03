# Frozen comparison and report example

This example uses self-authored analytic fixtures to exercise STK's normal headless API,
Files/Snapshots, saved AnalysisRun, graph worker, plots and Report/1. It does not run a solver,
read a paper, establish a physical result or change the visible project, Viewer or layout.

Use Python 3.11–3.14 with STK and its NumPy/Matplotlib plotting dependencies installed. From
the repository root, choose a **new** project directory and **new** export destination:

```bash
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= python -m examples.reproduction_comparison.offline prepare /tmp/stk-comparison-example
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= python -m examples.reproduction_comparison.offline read /tmp/stk-comparison-example
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= python -m examples.reproduction_comparison.offline start /tmp/stk-comparison-example
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= python -m examples.reproduction_comparison.offline read /tmp/stk-comparison-example
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= python -m examples.reproduction_comparison.offline report /tmp/stk-comparison-example
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= python -m examples.reproduction_comparison.offline export /tmp/stk-comparison-example --export /tmp/stk-comparison-evidence.zip
```

`prepare` freezes inputs and explicit tolerances but does not evaluate the graph. `start` is
the sole execution action. `read` verifies the original identities, frozen inputs, archived
outputs and any created report. `report` creates one file-backed Report/1; `export` separately
verifies and exports that existing report. Each CLI invocation uses temporary private service,
model-state and plotting-cache locations; it does not call hello/autostart or a model request.

The reference is `y = 2x` on `x = [0, 1, 2]`, labelled seconds and metres. Every comparison
freezes absolute tolerance `0.25`, relative tolerance `0`, exact alignment and domain `[0, 2]`.
No conversion or extrapolation is performed.

| Case | Authored observation | Expected comparison |
| --- | --- | --- |
| within_tolerance | `2x + 0.125` | passed; RMSE 0.125 |
| outside_tolerance | `2x + 0.5` | failed; RMSE 0.5 |
| missing_rows | one missing value and one failed row | indeterminate; all three rows retained |
| failed_run | explicitly failed source run | indeterminate |
| unit_mismatch | actual values labelled cm | indeterminate; no unit conversion |

The saved analysis can succeed while its comparison outputs are failed or indeterminate.
The archive contains all five comparison documents, five error tables, two actual PNGs and
two plot outputs with the exact plotted data blobs. The report's 18 assets preserve comparison
JSON, error tables, the exact archived graph-result bytes, execution/document evidence and
PNG/plot data. JSON is stored as UTF-8 `*.json.txt`, an existing Report/1 text asset type.

Original analysis/run/report UUIDs are saved before their actions. `run-request.json` records
the complete original preparation request and expected source identities before prepare. If
the prepare reply is lost, `read` queries that same run UUID and checks its complete request,
document and bindings; `prepare_response_received: false` is an observation, not a fabricated
acknowledgement. It never writes a replacement `prepared.json` or replays preparation.

After an uncertain start, use `read`, never regenerate the run ID or repeat the example under
another identity. After a lost report-create reply, use `read` and then the explicit `export`
action; it queries the original report UUID and checks the original complete asset selection.
An export failure may be followed by explicit export to another new destination. Existing
files are never overwritten. Failures leave their request notes and partial work for inspection.

`start` observes for at most 300 seconds. Observation timeout does not request cancellation;
closing the headless session does cancel its active local analysis. Keep a programmatic
session open while observing work. Reopen/recover do not execute it again.

Input and source labels remain unauthenticated scientific input. Report/1 verifies the local
project/run identity and its captured lifecycle; it does not authenticate paper authorship.
Inline archived error tables retain column order, values and units, but the existing graph
delivery does not include Field dtype/lossy descriptors. Missing floating values appear as
`"NaN"` in these table archives; the comparison JSON retains null missing values, original
markers and exact input values/descriptors. The ZIP is evidence export, not a project import.

See [the integration guide](../../docs/reproduction-comparison.md) and the
[comparison contract](../../docs/specs/reproduction-comparison-1.md).
