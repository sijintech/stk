"""Explicit local saved-analysis demo; run this file in STK's Python panel.

Creates a fresh project and synthetic CSV, freezes its inputs, prepares and starts ONE local
analysis. No Runtime, network, model, Viewer, project switch or layout change is requested.
"""
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
from uuid import uuid4

DIRECTORY = Path.home() / "STK Projects" / (
    "offline-analysis-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f") + "-" + uuid4().hex[:8])
WAIT_SECONDS = 60
HEADERS = ["step", "temperature_difference", "case", *[f"sample_{index}" for index in range(1, 8)]]
ROW_COUNT = 73
ACTIVE = {"running", "cancel_requested"}
REQUIRED_OPERATIONS = {
    "project.create", "project.snapshot", "project.files.index", "project.snapshots.capture",
    "project.analyses.create", "project.analysis_runs.prepare", "project.analysis_runs.start",
    "project.analysis_runs.get", "project.analysis_runs.result",
}


def _rows():
    differences = [-9.5, 0.0, 14.5]
    return [[step, differences[step] if step < 3 else (step - 36) / 2.0, f"synthetic-{step:03d}",
             *[step * (index + 1) for index in range(1, 8)]] for step in range(ROW_COUNT)]


def _write_json_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _observe(runs, run, wait_seconds):
    """Bound observation only. Never starts, retries, cancels or recovers an execution."""
    deadline = time.monotonic() + wait_seconds
    while run["status"] in ACTIVE:
        if time.monotonic() >= deadline:
            return run, True
        run = runs.get(run["id"])
        if run["status"] in ACTIVE:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(0.1, remaining))
    return run, False


def _check_table(archive):
    result = archive["result"]
    if result.get("errors") or set(result["outputs"]) != {"table"}:
        raise ValueError("The synthetic analysis did not return exactly one successful table")
    table = result["outputs"]["table"]
    if table.get("type") != "table" or "blob" in table or table.get("column_names") != HEADERS:
        raise ValueError("The synthetic result is not the expected ordered inline table")
    columns, rows = table["columns"], _rows()
    if set(columns) != set(HEADERS) or table["units"].get("temperature_difference") != "K":
        raise ValueError("Synthetic result columns or temperature-difference unit changed")
    for index, name in enumerate(HEADERS):
        expected = [row[index] for row in rows]
        actual = columns[name]
        kind = float if name == "temperature_difference" else str if name == "case" else int
        if actual != expected or any(type(value) is not kind for value in actual):
            raise ValueError(f"Synthetic column {name!r} differs in values or JSON types")


def create_demo(stk, directory, *, wait_seconds=WAIT_SECONDS):
    """Create a NEW offline sample and explicitly start its one local table analysis.

    The existing visible project and all other open project handles remain untouched. The
    destination must not exist, even if empty. Timeout stops observation, not the background run.
    """
    if type(wait_seconds) not in (int, float) or not math.isfinite(wait_seconds) or not 0 <= wait_seconds <= 300:
        raise ValueError("wait_seconds must be a finite number between 0 and 300")
    missing = REQUIRED_OPERATIONS - set(stk.operations()["operations"])
    if missing:
        raise RuntimeError("Update/rebuild STK; missing operations: " + ", ".join(sorted(missing)))
    # Do not resolve an existing dangling symlink into a new target. Exclusive creation of
    # the requested final path rejects every pre-existing directory/file/link first.
    directory = Path(os.path.abspath(Path(directory).expanduser()))
    directory.mkdir(parents=True, exist_ok=False)
    directory = directory.resolve()
    print("Synthetic local analysis / 合成本机分析:", directory, flush=True)
    p = stk.projects.create(directory, "Synthetic offline analysis / 合成离线分析")
    project_id = p.snapshot()["project"]["id"]
    csv_path = directory / "synthetic.csv"
    with csv_path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADERS)
        writer.writerows(_rows())
    document = {
        "format": "stk.analysis-document/1",
        "graph": {
            "schema": "stk.graph/1", "id": "synthetic-table-demo",
            "parameters": [{"name": "path", "type": "string", "default": "synthetic.csv"}],
            "nodes": [{"id": "source", "type": "stk.source.table@1",
                       "params": {"binding": "data", "path": {"$param": "path"}, "format": "csv",
                                  "units": {"temperature_difference": "K"}}}],
            "outputs": {"table": "source.out"},
        },
        "parameters": {"path": "synthetic.csv"}, "outputs": ["table"],
    }
    _write_json_new(directory / "analysis-document.json", document)
    with (directory / "README.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("# Synthetic local analysis / 合成本机分析\n\n"
                     "This is a software acceptance sample, not a physical simulation.\n"
                     "73 rows and 10 columns exercise row and column paging.\n"
                     "temperature_difference is a synthetic difference in K, not absolute temperature.\n"
                     "The first three differences are -9.5, 0.0 and 14.5.\n"
                     "demo.json records durable IDs before the single explicit start.\n"
                     "No Runtime tasks, remote services, model calls or Viewer import are used.\n"
                     "Open this project manually; Node Graph > Saved analysis > Definitions: load\n"
                     "the synthetic definition, then Runs > Refresh > select the recorded run >\n"
                     "Read and verify result > table > Table grid. Existing projects stay open\n"
                     "until you explicitly choose to switch.\n")
    indexed = p.files.index([csv_path], expected_revision=0)
    record_id = indexed["record_ids"][0]
    captured = p.snapshots.capture([record_id], expected_revision=indexed["revision"])
    snapshot_id = captured["snapshot"]["id"]
    analysis_id, run_id = str(uuid4()), str(uuid4())
    saved = p.analyses.create("Synthetic CSV / 合成 CSV", document, analysis_id=analysis_id,
                              expected_revision=captured["revision"])
    bindings = {"data": {"synthetic.csv": record_id}}
    run = p.analysis_runs.prepare(analysis_id, snapshot_id, bindings, run_id=run_id,
                                  expected_revision=saved["revision"])
    receipt = {"directory": str(directory), "project_id": project_id, "analysis_id": analysis_id,
               "run_id": run_id, "snapshot_id": snapshot_id, "record_id": record_id,
               "revision": saved["revision"], "plan_sha256": run["plan_sha256"], "bindings": bindings,
               "synthetic": True, "rows": ROW_COUNT, "columns": list(HEADERS)}
    # Immutable identification note, intentionally written before start. Never rewrite it with
    # a guessed lifecycle status: the journal is the authority after interruption or timeout.
    _write_json_new(directory / "demo.json", receipt)
    print("Prepared run:", run_id, "\nAnalysis:", analysis_id, "\nSnapshot:", snapshot_id, flush=True)
    print("Starting ONE local table analysis now; existing projects and Viewer remain unchanged.", flush=True)
    run = p.analysis_runs.start(run_id)
    run, timed_out = _observe(p.analysis_runs, run, wait_seconds)
    summary = {**receipt, "status": run["status"], "observation_timed_out": timed_out, "verified_result": False}
    if timed_out:
        print("Observation timed out; this does NOT cancel execution. Refresh the saved run explicitly.", flush=True)
    elif run["status"] == "succeeded" and run["result"] is not None:
        archive = p.analysis_runs.result(run_id)
        _check_table(archive)
        summary["verified_result"] = True
        summary["manifest_sha256"] = archive["run"]["result"]["manifest_sha256"]
        print("Verified synthetic inline table: 73 rows × 10 columns; first differences -9.5, 0.0, 14.5 K.", flush=True)
    else:
        raise RuntimeError(f"Synthetic local analysis ended as {run['status']}: {run.get('error')}. "
                           f"Keep {directory / 'demo.json'} and inspect the saved run; it was not retried.")
    print("Open this NEW project manually when ready:", directory, flush=True)
    print("Node Graph / 分析图 → Saved analysis / 保存的分析 → load Synthetic CSV → Runs / 运行 → "
          "Refresh and select the run → Read and verify result → table → Table grid / 表格视图.", flush=True)
    return summary


if __name__ == "__main__":
    if "stk" not in globals():
        raise SystemExit("Run offline.py explicitly from STK: File → Python → Run file")
    offline_analysis_demo = create_demo(stk, DIRECTORY, wait_seconds=WAIT_SECONDS)
