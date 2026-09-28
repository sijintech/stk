"""Run explicitly in STK's Python panel: create a project, freeze/upload inputs, prepare three runs.

Edit CONNECTION before running. This script creates workspaces and transfers files but never
submits a simulation. Use the native Runs panel to inspect and submit each saved plan.
"""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from uuid import uuid4

CONNECTION = "runtime:lab"  # An existing direct or managed-SSH Runtime profile in Jobs.
DIRECTORY = Path.home() / "STK Projects" / ("temperature-scan-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
TEMPERATURES = [300, 325, 350]


def prepare(stk, directory, connection, temperatures=TEMPERATURES, *, show_ui=True):
    if connection.startswith("hub:"):
        raise ValueError("This minimal example uses a direct/SSH Runtime profile; Hub reviews require a separate preparation flow")
    temperatures = list(temperatures)
    if not 1 <= len(temperatures) <= 32 or any(type(t) not in (int, float) or not math.isfinite(t) or not 0 < t <= 10000 for t in temperatures):
        raise ValueError("Provide 1–32 finite temperatures between 0 and 10000 K")
    directory = Path(directory).expanduser().resolve()
    p = stk.projects.create(directory, "Temperature scan / 温度扫描")
    print("Project:", directory, flush=True)
    if show_ui:
        stk.ui.open_project(directory)
    project_id = p.snapshot()["project"]["id"]
    table, field = str(uuid4()), str(uuid4())
    rows = [str(uuid4()) for _ in temperatures]
    commands = [{"op": "create_table", "id": table, "name": "Cases / 参数"},
                {"op": "add_field", "id": field, "table_id": table, "name": "Temperature", "type": "number", "unit": "K"}]
    for row, temperature in zip(rows, temperatures):
        commands.extend([{"op": "add_record", "id": row, "table_id": table},
                         {"op": "set_cell", "table_id": table, "record_id": row, "field_id": field, "value": temperature}])
    revision = p.apply(commands, expected_revision=0)["revision"]
    inputs = directory / "inputs"
    inputs.mkdir()
    program = inputs / "solver.py"
    program.write_bytes(Path(__file__).with_name("solver.py").read_bytes())
    paths = [program]
    for row, temperature in zip(rows, temperatures):
        path = inputs / row / "input.json"
        path.parent.mkdir()
        path.write_text(json.dumps({"temperature_K": temperature, "size": 17}) + "\n", encoding="utf-8")
        paths.append(path)
    indexed = p.files.index(paths, expected_revision=revision)
    revision, file_ids = indexed["revision"], indexed["record_ids"]
    runtime = stk.runtime(connection)
    entries = []
    for row, temperature, file_id in zip(rows, temperatures, file_ids[1:]):
        capture = p.snapshots.capture([file_ids[0], file_id], expected_revision=revision)
        revision, snapshot_id = capture["revision"], capture["snapshot"]["id"]
        key = f"scan:{project_id}:{row}"
        workspace = runtime.workspaces.create(f"Synthetic field {temperature} K", idempotency_key=key + ":workspace")["workspace"]["id"]
        for remote, identity in (("solver.py", file_ids[0]), ("input.json", file_id)):
            source = p.snapshots.resolve(snapshot_id, identity)["path"]
            transfer = runtime.upload(workspace, source, remote=remote, idempotency_key=key + ":" + remote)
            transfer = stk.transfers.wait(transfer["id"], timeout=120)
            if transfer["state"] != "completed":
                raise RuntimeError(f"Input transfer stopped: {transfer['id']} ({transfer['state']}); inspect Transfers")
        entries.append({"table_id": table, "record_id": row, "label": f"Synthetic field / 演示场 {temperature} K",
                        "input_snapshot_id": snapshot_id, "input_bindings": {"solver.py": file_ids[0], "input.json": file_id},
                        "spec": {"workspace_id": workspace, "argv": ["{python}", "solver.py"],
                                 "outputs": ["metrics.json", "field.vtk", "slice.png"], "name": f"Synthetic {temperature} K"}})
    prepared = p.runs.prepare(entries, connection=connection, expected_revision=revision)
    print("Prepared; no simulations submitted:", prepared["run_ids"], flush=True)
    return {"directory": str(directory), "project_id": project_id, "table_id": table, "field_id": field,
            "record_ids": rows, "run_ids": prepared["run_ids"]}


if __name__ == "__main__":
    if "stk" not in globals():
        raise SystemExit("Open this file in STK's Python panel, set CONNECTION, then explicitly run it")
    prepared_scan = prepare(stk, DIRECTORY, CONNECTION)
