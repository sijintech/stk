"""Manual acceptance (not CI): real LAMMPS through the project workflow on a local Runtime.

Run from the repository root after building ``pet-case/pet.data`` (see ../README.md):

    STK_LAMMPS=/path/to/lmp PYTHONPATH=tests env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= \
        python -m pytest examples/pet_lammps/acceptance -p conftest --rootdir=examples/pet_lammps/acceptance -s -p no:cacheprovider

Without ``STK_LAMMPS`` it uses the STK module's ``lmp``; a missing program or data file fails rather than skips.
"""
from pathlib import Path
from uuid import uuid4
import os
import pytest
from suan.modules import find_program
from suan.project import ProjectStore
from suan.scripting import API
from suan.workflows import lammps
from test_bridge_workflow_muferro import settled, tasks
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_desktop_bridge_runtime import add_profile

HERE = Path(__file__).parent


def program():
    lmp = os.environ.get("STK_LAMMPS") or find_program("lammps")
    assert lmp and Path(lmp).exists(), "no LAMMPS: set STK_LAMMPS or install the lammps module"
    return str(lmp)


@pytest.mark.parametrize("case, rows", [("lj-case", [("temperature", 2.0), ("temperature", 3.0)]),
                                        ("pet-case", [("temperature", 450), ("temperature", 550)])])
def test_real_lammps(inproc, runtime, tmp_path, case, rows):
    lmp = program()
    if case == "pet-case":
        assert (HERE / case / "pet.data").exists(), "build pet-case/pet.data with build_pet.py first"
    client, supervisor, _, _ = runtime
    h = inproc()
    connection = add_profile(h, runtime)
    store = ProjectStore.create(tmp_path / "project", case)
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    api = API(lambda op, params: h.call(op, params)); api._project_handle = handle
    first = api.lammps.import_case(HERE / case, expected_revision=store.info()["revision"])["record_id"]
    ids = [first, api.lammps.clone_case(first, expected_revision=store.info()["revision"])["record_id"]]
    for row, (key, value) in zip(ids, rows):
        store.apply([{"op": "set_cell", "table_id": lammps.TABLE_ID, "record_id": row, "field_id": lammps.FIELD_IDS[key],
                      "value": value}], expected_revision=store.info()["revision"])
    workflow = str(uuid4())
    store.workflows.create("scan", {"format": "stk.workflow/1", "ui": {}, "steps": [
        {"id": "cases", "kind": "table", "ref": {"table": lammps.TABLE_ID}},
        {"id": "simulate", "kind": "simulation", "ref": {"template": "lammps/1"}, "inputs": {"rows": {"from": "cases.rows"}}}]},
        workflow_id=workflow, expected_revision=store.info()["revision"])
    h.bridge.workflow_executor.poll_seconds = 0.05
    run = h.call("project.workflow_runs.prepare", {"handle": handle, "workflow_id": workflow, "rows": ids, "run_id": str(uuid4()),
        "expected_revision": store.info()["revision"], "simulation": {"connection": connection, "options": {"program": lmp}}})["run"]
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    s = {"h": h, "handle": handle, "supervisor": supervisor}
    done = settled(s, run["id"], timeout=900)
    assert done["complete"], done["tasks"]
    results = next(t for t in store.snapshot()["tables"] if t["id"] == lammps.RESULT_TABLE_ID)
    f = lammps.RESULT_FIELD_IDS
    assert len(results["records"]) == 2
    for r in results["records"]:
        v = r["values"]
        print(case, "T set", v[f["temperature"]], "units", v[f["units"]], "T mean", round(v[f["temperature_mean"]], 3),
              "density", v[f["density"]] and round(v[f["density"]], 4), "PE", v[f["potential_energy"]], "columns", v[f["thermo"]]["columns"],
              "step", v[f["step"]], "files", len(v[f["files"]]))
    produced = tasks(done)[("simulate", ids[0])]["produced"]
    print(case, "final state:", sorted(produced["files"]))
