"""Explicit local workbench demo: no Runtime server, SSH profile or remote task is required.

Run this file in the desktop Python panel. Each execution creates a fresh project; it does not
update existing simulations. The field is synthetic, not a scientific solver.
"""
import copy
import csv
from datetime import datetime, timezone
import importlib.util
import json
import math
import time
from pathlib import Path
from uuid import uuid4

DIRECTORY = Path.home() / "STK Projects" / ("offline-workbench-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))


def _write_csv(path, headers, rows):
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)


def _solver():
    source = Path(__file__).with_name("solver.py")
    spec = importlib.util.spec_from_file_location("stk_offline_synthetic_solver", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, source


def create_demo(stk, directory, *, show_ui=True, analyze=True):
    directory = Path(directory).expanduser().resolve()
    previous_layout = stk.ui.layout() if show_ui else None
    p = stk.projects.create(directory, "Offline workbench / 离线工作台")
    print("Offline project:", directory, flush=True)
    inputs = directory / "inputs"
    inputs.mkdir()
    source_csv = inputs / "cases.csv"
    _write_csv(source_csv, ["Case", "Temperature", "Enabled"],
               [["A", 300, "true"], ["B", 325, "true"], ["C", 350, "true"]])
    imported = p.csv.import_file(source_csv, name="Cases / 参数", types={"Temperature": "number", "Enabled": "boolean"},
                                 units={"Temperature": "K"}, expected_revision=0)
    table, temperature = imported["table_id"], imported["field_ids"][1]
    controls, offset, control_row, effective = (str(uuid4()) for _ in range(4))
    commands = [
        {"op": "create_table", "id": controls, "name": "Controls / 公共参数"},
        {"op": "add_field", "table_id": controls, "id": offset, "name": "Offset", "type": "number", "unit": "K"},
        {"op": "add_record", "table_id": controls, "id": control_row},
        {"op": "set_cell", "table_id": controls, "record_id": control_row, "field_id": offset, "value": 10},
        {"op": "add_field", "table_id": table, "id": effective, "name": "Effective temperature", "type": "number", "unit": "K"},
    ]
    for row in imported["record_ids"]:
        commands.append({"op": "set_expression", "table_id": table, "record_id": row, "field_id": effective,
                         "expression": "base + offset", "bindings": {
                             "base": {"record_id": row, "field_id": temperature},
                             "offset": {"record_id": control_row, "field_id": offset}}})
    revision = p.apply(commands, expected_revision=imported["revision"])["revision"]
    snapshot = p.snapshot()
    cases = next(item for item in snapshot["tables"] if item["id"] == table)
    solver, solver_source = _solver()
    program = inputs / "solver.py"
    program.write_bytes(solver_source.read_bytes())
    paths, frozen_files, results, folders = [source_csv, program], [source_csv, program], [], []
    graph = {
        "schema": "stk.graph/1", "id": "offline-statistics", "catalog": {"stk": 1},
        "nodes": [
            {"id": "source", "type": "stk.source.file@1", "params": {"binding": "data", "path": "field.vtk"}},
            {"id": "statistics", "type": "stk.analysis.statistics@1", "inputs": {"in": {"from": "source.out"}},
             "params": {"fields": ["response"], "components": "each"}},
        ], "outputs": {"statistics": "statistics.out"},
    }
    graph_path = directory / "analysis.graph.json"
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths.append(graph_path)
    frozen_files.append(graph_path)
    if analyze:
        checked = stk.graph.validate(graph)
        if not checked["ok"]:
            raise ValueError(checked["issues"])
    for index, row in enumerate(cases["records"]):
        values = row["values"]
        config = {"temperature_K": values[effective], "size": 17}
        input_file = inputs / f"case-{index + 1}.json"
        input_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        paths.append(input_file)
        frozen_files.append(input_file)
        output = directory / "results" / f"case-{index + 1}"
        metrics = solver.simulate(config, output)
        folders.append(str(output))
        paths.extend(output / name for name in ("field.vtk", "metrics.json", "slice.png"))
        if analyze:
            evaluated = stk.graph.evaluate({"graph": graph, "outputs": ["statistics"]},
                                           eval_id=uuid4().hex, local_bindings={"data": output})
            result = evaluated["result"]
            if result.get("errors"):
                raise ValueError(result["errors"])
            statistics = result["outputs"]["statistics"]["columns"]
            if not (statistics["count"] == [17 ** 3] and statistics["nan_count"] == [0]
                    and math.isclose(statistics["mean"][0], metrics["mean_K"], rel_tol=1e-12)
                    and math.isclose(statistics["max"][0], metrics["max_K"], rel_tol=1e-12)):
                raise ValueError("Independent graph statistics disagree with the generated field")
            report = output / "analysis.json"
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            paths.append(report)
        results.append([values[imported["field_ids"][0]], row["id"], values[temperature], values[effective],
                        metrics["mean_K"], metrics["max_K"], str(output.relative_to(directory))])
    results_csv = directory / "results-summary.csv"
    _write_csv(results_csv, ["Case", "Source record", "Input temperature", "Effective temperature", "Mean", "Maximum", "Directory"], results)
    paths.append(results_csv)
    numeric = {name: "number" for name in ("Input temperature", "Effective temperature", "Mean", "Maximum")}
    summary = p.csv.import_file(results_csv, name="Results / 结果", types=numeric,
                               units={name: "K" for name in numeric}, expected_revision=revision)
    revision = summary["revision"]
    notes = directory / "README.md"
    notes.write_text("# Offline synthetic workbench demo / 离线合成场演示\n\n"
                     "Three synthetic fields use Temperature + the shared Offset (10 K).\n"
                     "This is a local UI/data demonstration, not a physical solver or Runtime run.\n"
                     "Editing a table recomputes dependent cells, but never silently reruns the generated fields.\n"
                     "Input files and program have an immutable snapshot; outputs remain the original local samples.\n"
                     "See analysis.graph.json for the explicit source → statistics node connection.\n", encoding="utf-8")
    paths.append(notes)
    if previous_layout is not None:
        layout_path = directory / "layout-before-demo.json"
        layout_path.write_text(json.dumps(previous_layout, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths.append(layout_path)
    indexed = p.files.index(paths, expected_revision=revision)
    by_path = dict(zip(paths, indexed["record_ids"]))
    captured = p.snapshots.capture([by_path[path] for path in frozen_files], expected_revision=indexed["revision"])
    result = {"directory": str(directory), "project_id": snapshot["project"]["id"], "table_id": table,
              "record_ids": imported["record_ids"], "effective_field": effective, "control_table": controls,
              "control_record": control_row, "offset_field": offset, "result_table": summary["table_id"],
              "folders": folders, "snapshot_id": captured["snapshot"]["id"], "revision": captured["revision"],
              "previous_layout": previous_layout}
    if show_ui:
        stk.ui.open_project(directory)
        layout = copy.deepcopy(previous_layout)
        layout["screen"] = {"maximized": None, "root": {"factor": 1, "split": "horizontal", "children": [
            {"factor": 0.48, "area": {"id": "demo-project", "type": "project"}},
            {"factor": 0.52, "split": "vertical", "children": [
                {"factor": 0.65, "area": {"id": "demo-view", "type": "viewer"}},
                {"factor": 0.35, "area": {"id": "demo-python", "type": "python"}},
            ]},
        ]}}
        stk.ui.apply_layout(layout)
        deadline = time.monotonic() + 30
        while True:
            presets = stk.viewer.presets()
            if presets["error"]:
                raise RuntimeError(presets["error"])
            if presets["ready"]:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Viewer presets did not become ready")
            time.sleep(0.05)
        stk.viewer.configure(auto_evaluate=True, prefetch=False)
        stk.viewer.open(folders[-1], preset="volume", parameters={"path": "field.vtk", "range": [0, 400]})
        shown = stk.viewer.wait(timeout=120)
        if shown["error"] or shown["metadata_error"] or not shown["has_payload"]:
            raise RuntimeError(shown["error"] or shown["metadata_error"] or "No Viewer payload was produced")
    print("Ready: parameters, shared formulas, local fields, result table, file index and frozen inputs.", flush=True)
    print("Changing a parameter updates formulas; this demo does not automatically regenerate output files.", flush=True)
    return result


if __name__ == "__main__":
    if "stk" not in globals():
        raise SystemExit("Run offline.py explicitly in STK's Python panel after updating the desktop")
    offline_demo = create_demo(stk, DIRECTORY)
