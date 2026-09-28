"""Explicitly show the latest collected demo result in the shared native Viewer."""
import math
from pathlib import Path


def show_directory(stk, directory, *, maximum=400, focus=True):
    if type(maximum) not in (int, float) or not math.isfinite(maximum) or maximum <= 0:
        raise ValueError("maximum must be a positive finite value")
    stk.viewer.configure(auto_evaluate=True, prefetch=False)
    stk.viewer.open(directory, preset="volume", parameters={"path": "field.vtk", "range": [0, maximum]}, focus=focus)
    status = stk.viewer.wait(timeout=120)
    if status["error"] or status["metadata_error"] or not status["has_payload"]:
        raise RuntimeError(status["error"] or status["metadata_error"] or "Viewer did not produce a payload")
    print("Viewer:", status["source"]["path"], "—", len(status["layers"]), "layers", flush=True)
    return status


def show_latest(stk):
    p = stk.project
    info = next(info for info in stk.projects.list() if info["handle"] == p.handle)
    runs, offset = [], 0
    while True:
        page = p.runs.list(offset=offset)
        runs.extend(run for run in page["runs"] if run["label"].startswith("Synthetic field / 演示场 "))
        if page["next_offset"] is None:
            break
        offset = page["next_offset"]
    # Inspect local collection results only; opening a view never submits a simulation.
    ready = [run for run in runs if run["task_state"] == "succeeded"
             and (Path(info["directory"]) / "results" / run["id"] / "field.vtk").is_file()]
    if not ready:
        raise ValueError("Collect at least one successful demo result before running show.py")
    maximum = 0
    for run in runs:
        frozen = p.runs.get(run["id"])["plan"]["parameters"]
        field = next(field["id"] for field in frozen["fields"] if field["name"] == "Temperature")
        maximum = max(maximum, frozen["values"][field])
    return show_directory(stk, Path(info["directory"]) / "results" / ready[-1]["id"], maximum=maximum)


if __name__ == "__main__":
    if "stk" not in globals():
        raise SystemExit("Select the collected demo project, then explicitly run this file in STK's Python panel")
    shown_scan = show_latest(stk)
