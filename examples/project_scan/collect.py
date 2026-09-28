"""Run explicitly in the STK Python panel after submitting the demo runs.

Refresh accepted runs, download successful outputs, and update a stable-ID result table.
Prepared/pending/failed runs are reported and left alone; this script never submits a task.
"""
import hashlib
import json
import math
from pathlib import Path
from uuid import UUID, uuid5

OUTPUTS = ("metrics.json", "field.vtk", "slice.png")


def collect(stk, project=None):
    p = project or stk.project
    info = next(info for info in stk.projects.list() if info["handle"] == p.handle)
    directory, project_id = Path(info["directory"]), info["id"]
    def identity(name):
        return str(uuid5(UUID(project_id), "temperature-scan-result:" + name))
    table_id = identity("table")
    fields = [("run", "Run ID", "text", None), ("temperature", "Temperature", "number", "K"),
              ("mean", "Mean response", "number", "K"), ("max", "Maximum response", "number", "K"),
              ("files", "Result files", "json", None)]
    summaries, offset = [], 0
    while True:
        page = p.runs.list(offset=offset)
        summaries.extend(page["runs"])
        if page["next_offset"] is None:
            break
        offset = page["next_offset"]
    results = []
    for summary in summaries:
        run = p.runs.get(summary["id"])
        plan = run["plan"]
        if not plan["label"].startswith("Synthetic field / 演示场 "):
            continue
        run = p.runs.refresh(run["id"])
        task = run["status"].get("task")
        if not task or task["state"] != "succeeded":
            print(plan["label"], "—", task["state"] if task else run["status"]["submission"], flush=True)
            continue
        runtime = stk.runtime(plan["connection"], node=plan["node"])
        artifacts = {item["path"]: item for item in runtime.tasks.artifacts(task["id"])}
        if not set(OUTPUTS) <= set(artifacts) or artifacts["metrics.json"]["size"] > 1024 * 1024:
            raise ValueError("Successful demo task has missing outputs or an unexpectedly large metrics file")
        destination = directory / "results" / run["id"]
        destination.mkdir(parents=True, exist_ok=True)
        paths, metrics_bytes = [], b""
        for name in OUTPUTS:
            path = destination / name
            transfer = runtime.download(name, task_id=task["id"], dest=path,
                                        idempotency_key=f"scan:{project_id}:{run['id']}:result:{name}")
            transfer = stk.transfers.wait(transfer["id"], timeout=120)
            if transfer["state"] != "completed":
                raise RuntimeError(f"Result transfer stopped: {transfer['id']} ({transfer['state']}); inspect Transfers")
            # A completed transfer records what arrived then; users may have edited/deleted
            # the local file afterwards. Verify the current bytes before parsing/indexing them.
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
                    if name == "metrics.json":
                        metrics_bytes += block
                        if len(metrics_bytes) > 1024 * 1024:
                            raise ValueError("Local metrics file exceeds the demo limit")
            if path.stat().st_size != artifacts[name]["size"] or digest.hexdigest() != artifacts[name]["sha256"]:
                raise ValueError(f"Downloaded result changed locally: {path}; download again with a new transfer key")
            paths.append(path)
        metrics = json.loads(metrics_bytes.decode("utf-8"))
        temperature_field = next(field["id"] for field in plan["parameters"]["fields"] if field["name"] == "Temperature")
        temperature = plan["parameters"]["values"][temperature_field]
        if (metrics.get("format") != 1 or metrics.get("synthetic") is not True or metrics.get("temperature_K") != temperature
                or any(type(metrics.get(key)) not in (int, float) or not math.isfinite(metrics[key]) for key in ("mean_K", "max_K"))):
            raise ValueError("Downloaded metrics do not match the frozen demo parameters")
        p.files.index(paths, expected_revision=p.snapshot()["project"]["revision"])
        model = p.snapshot()
        table = next((table for table in model["tables"] if table["id"] == table_id), None)
        commands = []
        if table is None:
            commands.append({"op": "create_table", "id": table_id, "name": "Results / 结果比较"})
            commands.extend({"op": "add_field", "id": identity(key), "table_id": table_id, "name": name,
                             "type": kind, **({"unit": unit} if unit else {})} for key, name, kind, unit in fields)
        else:
            actual = {field["id"]: (field["type"], field.get("unit")) for field in table["fields"]}
            if any(actual.get(identity(key)) != (kind, unit) for key, _, kind, unit in fields):
                raise ValueError("The existing demo result table has incompatible fields; inspect it before collecting again")
        row_id = identity(run["id"])
        if table is None or not any(row["id"] == row_id for row in table["records"]):
            commands.append({"op": "add_record", "id": row_id, "table_id": table_id})
        values = {"run": run["id"], "temperature": temperature, "mean": metrics["mean_K"], "max": metrics["max_K"],
                  "files": [path.relative_to(directory).as_posix() for path in paths]}
        commands.extend({"op": "set_cell", "table_id": table_id, "record_id": row_id, "field_id": identity(key), "value": value}
                        for key, value in values.items())
        p.apply(commands, expected_revision=model["project"]["revision"])
        print(f"{temperature:g} K: mean={metrics['mean_K']:.6f} K, max={metrics['max_K']:.6f} K; VTK: {paths[1]}", flush=True)
        results.append({"run_id": run["id"], "metrics": metrics, "paths": [str(path) for path in paths]})
    print(f"Collected {len(results)} successful runs into Results / 结果比较. No tasks submitted.", flush=True)
    return results


if __name__ == "__main__":
    if "stk" not in globals():
        raise SystemExit("Select the demo project, then explicitly run this file in STK's Python panel")
    collected_scan = collect(stk)
