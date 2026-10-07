"""A ready-to-explore example project, built offline in seconds.

Entry points: ``suan demo [DIRECTORY]``, Home → "Create example project" in the desktop, or
``create_demo(stk)`` from the desktop console or a headless session. Without a directory it makes
``stk-example-<time>`` under ``$STK_PROJECTS_DIR`` (default ``~/STK Projects``). It walks the main path once:

1. "Cases / 算例" gets a temperature field and three rows from a parameter sweep (300, 325, 350 K);
2. a synthetic solver on this computer writes ``results/demo/case-N/field.vtk`` and ``metrics.json``
   for each row: a smooth 3D field scaled by the temperature, **not a physical simulation**;
3. "Results / 结果" records each case's mean and maximum, its first cell a reference to the case;
4. the three field files are registered in the file index and frozen as one input snapshot;
5. the saved analysis "Temperature field / 温度场" (the volume preset) gets one local run of the
   hottest case, started and observed here, so Analysis → Runs can show it right away;
6. the workflow "Temperature scan / 温度扫描" (experimental ``stk.workflow/1``) links the cases table,
   the synthetic solver as a local step (``demo-synthetic/1``, temperature from each row) and the saved
   analysis; it is only defined here, and runs per row when started explicitly (``stk.project.workflow_runs``).

Nothing contacts a Runtime, a server or a model. Real simulations run on a Linux Runtime
(see docs/quickstart-linux.md).
"""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
from uuid import uuid4

__all__ = ["TEMPERATURES", "create_demo", "synthetic_field", "workflow_document"]

TEMPERATURES = (300, 325, 350)
GRID = 17
_ACTIVE = {"prepared", "running", "cancel_requested"}


def synthetic_field(temperature, directory, size=GRID):
    """Write field.vtk (point scalars ``response``) and metrics.json; returns the metrics."""
    axis = [i / (size - 1) for i in range(size)]
    values = [temperature * math.exp(-12 * ((x - .5) ** 2 + (y - .5) ** 2 + (z - .5) ** 2))
              for z in axis for y in axis for x in axis]
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    spacing = " ".join([format(1 / (size - 1), ".17g")] * 3)
    header = ("# vtk DataFile Version 3.0\nSTK example field (synthetic, not a simulation)\nASCII\n"
              f"DATASET STRUCTURED_POINTS\nDIMENSIONS {size} {size} {size}\nORIGIN 0 0 0\nSPACING {spacing}\n"
              f"POINT_DATA {len(values)}\nSCALARS response double 1\nLOOKUP_TABLE default\n")
    (directory / "field.vtk").write_text(header + "\n".join(format(v, ".17g") for v in values) + "\n", encoding="ascii")
    metrics = {"format": 1, "synthetic": True, "temperature_K": temperature, "shape": [size] * 3,
               "mean_K": math.fsum(values) / len(values), "max_K": max(values)}
    (directory / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return metrics


def _volume_document():
    preset = json.loads((Path(__file__).resolve().parents[1] / "graph" / "presets" / "volume.json").read_text(encoding="utf-8"))
    return {"format": "stk.analysis-document/1", "graph": preset["graph"],
            "parameters": {"path": "field.vtk"}, "outputs": ["view"]}


def workflow_document(cases_table, temperature_field, analysis_id):
    """Cases → synthetic solver (each row's temperature) → Temperature field, laid out left to right."""
    return {"format": "stk.workflow/1", "steps": [
        {"id": "cases", "kind": "table", "ref": {"table": cases_table}},
        {"id": "simulate", "kind": "simulation", "ref": {"template": "demo-synthetic/1"},
         "inputs": {"rows": {"from": "cases.rows"}}, "parameters": {"temperature": {"$field": temperature_field}}},
        {"id": "temperature", "kind": "analysis", "ref": {"analysis": analysis_id},
         "inputs": {"data": {"from": "simulate.files"}}},
    ], "ui": {"positions": {"cases": [0, 0], "simulate": [260, 0], "temperature": [520, 0]}}}


def _cell(table, record, field, value):
    return {"op": "set_cell", "table_id": table, "record_id": record, "field_id": field, "value": value}


def create_demo(stk, directory=None, *, wait_seconds=120):
    """Build the example project in a new (or empty) folder and return what was made."""
    root = Path(os.environ.get("STK_PROJECTS_DIR") or Path.home() / "STK Projects").expanduser()
    directory = Path(directory).expanduser() if directory else root / (
        "stk-example-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    if directory.exists() and any(directory.iterdir()):
        raise ValueError(f"Choose a new or empty folder for the example project; {directory} is not empty")
    p = stk.projects.create(directory, "STK example / 示例项目")
    try:
        cases, name, temperature = (str(uuid4()) for _ in range(3))
        revision = p.apply([
            {"op": "create_table", "id": cases, "name": "Cases / 算例"},
            {"op": "add_field", "id": name, "table_id": cases, "name": "Case / 算例", "type": "text"},
            {"op": "add_field", "id": temperature, "table_id": cases, "name": "Temperature / 温度", "type": "number", "unit": "K"},
        ], expected_revision=0)["revision"]
        swept = p.sweep(cases, [{"field_id": temperature, "values": list(TEMPERATURES)}], expected_revision=revision)
        rows = swept["record_ids"]
        revision = p.apply([_cell(cases, row, name, f"case-{i + 1}") for i, row in enumerate(rows)],
                           expected_revision=swept["revision"])["revision"]

        results, case, mean, maximum = (str(uuid4()) for _ in range(4))
        fields, commands = [], [
            {"op": "create_table", "id": results, "name": "Results / 结果"},
            {"op": "add_field", "id": case, "table_id": results, "name": "Case / 算例", "type": "text"},
            {"op": "add_field", "id": mean, "table_id": results, "name": "Mean / 平均", "type": "number", "unit": "K"},
            {"op": "add_field", "id": maximum, "table_id": results, "name": "Maximum / 最大", "type": "number", "unit": "K"},
        ]
        for i, (row, value) in enumerate(zip(rows, TEMPERATURES)):
            folder = directory / "results" / "demo" / f"case-{i + 1}"
            metrics = synthetic_field(value, folder)
            fields.append(folder / "field.vtk")
            result = str(uuid4())
            commands += [{"op": "add_record", "id": result, "table_id": results},
                         {"op": "set_reference", "table_id": results, "record_id": result, "field_id": case,
                          "source": {"record_id": row, "field_id": name}},
                         _cell(results, result, mean, round(metrics["mean_K"], 6)),
                         _cell(results, result, maximum, round(metrics["max_K"], 6))]
        revision = p.apply(commands, expected_revision=revision)["revision"]

        indexed = p.files.index(fields, expected_revision=revision)
        captured = p.snapshots.capture(indexed["record_ids"], expected_revision=indexed["revision"])
        analysis_id, run_id = str(uuid4()), str(uuid4())
        saved = p.analyses.create("Temperature field / 温度场", _volume_document(), analysis_id=analysis_id,
                                  expected_revision=captured["revision"])
        bindings = {"data": {"field.vtk": indexed["record_ids"][-1]}}
        p.analysis_runs.prepare(analysis_id, captured["snapshot"]["id"], bindings, run_id=run_id,
                                expected_revision=saved["revision"])
        workflow_id = str(uuid4())
        p.workflows.create("Temperature scan / 温度扫描",
                           workflow_document(cases, temperature, analysis_id),
                           workflow_id=workflow_id, expected_revision=saved["revision"])
        run = p.analysis_runs.start(run_id)
        deadline = time.monotonic() + wait_seconds
        while run["status"] in _ACTIVE and time.monotonic() < deadline:
            time.sleep(0.2)
            run = p.analysis_runs.get(run_id)
        (directory / "README.md").write_text(
            "# STK example project / 示例项目\n\n"
            "Synthetic data for trying STK, **not a physical simulation**. / 用于试用的合成数据，不是物理模拟。\n\n"
            "- Cases / 算例: three temperatures made by *Generate a parameter scan* / 由“生成参数扫描”生成。\n"
            "- results/demo/case-N: field.vtk and metrics.json from a synthetic solver on this computer.\n"
            "- Results / 结果: mean and maximum per case; the first column references the case row.\n"
            "- Node Graph → Saved analysis → Temperature field → Runs: a finished run of case-3; "
            "*Read and verify result*, then *Show selected output*, or *Run and show* for another file.\n"
            "- Home → Workflows: *Temperature scan* links the cases, the synthetic solver and the analysis; "
            "*Open analysis* enters it and the breadcrumb leads back. Started explicitly, it runs per row.\n",
            encoding="utf-8")
        return {"directory": str(directory), "project_id": p.snapshot()["project"]["id"], "cases_table": cases,
                "results_table": results, "analysis_id": analysis_id, "run_id": run_id, "run_status": run["status"],
                "workflow_id": workflow_id}
    finally:
        try:
            stk.call("project.close", handle=p.handle)
        except Exception:  # noqa: BLE001 - the project stays usable; closing this handle is best effort.
            pass
