"""LAMMPS cases in the project (E1a): import a case folder, set the parameters per row, run the rows as a workflow
step on a real local Runtime (the second engine through the per-row dispatch of E0a), collect verified results.
The solver is the fake LAMMPS of lammps_fake.py (no physics)."""
import os
from pathlib import Path
from uuid import uuid4

import pytest

from lammps_fake import make_fake_lammps, write_case
from suan.project import ProjectStore
from suan.scripting import API
from suan.workflows import lammps
from suan.workflows.templates import remote_templates
from test_bridge_workflow_muferro import get, settled, tasks, until  # noqa: F401
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_desktop_bridge_runtime import add_profile

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the fake LAMMPS is a script with a shebang line")


def cell(store, row, key, value):
    store.apply([{"op": "set_cell", "table_id": lammps.TABLE_ID, "record_id": row, "field_id": lammps.FIELD_IDS[key],
                  "value": value}], expected_revision=store.info()["revision"])


@pytest.fixture
def scan(inproc, runtime, tmp_path, monkeypatch):
    """Two rows of one imported case (300 K and 400 K at 1 atm) and a workflow cases -> LAMMPS."""
    client, supervisor, _, _ = runtime
    for name in ("STK_ALLOW_LOCAL_MPI", "STK_MUPRO_ALLOW_LOCAL_MPI", "SLURM_JOB_ID", "PBS_JOBID"):
        monkeypatch.delenv(name, raising=False)
    program = make_fake_lammps(tmp_path / "bin")
    h = inproc()
    connection = add_profile(h, runtime)
    store = ProjectStore.create(tmp_path / "project", "PET density")
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    api = API(lambda operation, params: h.call(operation, params))
    api._project_handle = handle
    imported = api.lammps.import_case(write_case(tmp_path / "pet-npt"), expected_revision=store.info()["revision"])
    first = imported["record_id"]
    cell(store, first, "pressure", 1.0)
    second = api.lammps.clone_case(first, expected_revision=store.info()["revision"])["record_id"]
    cell(store, second, "temperature", 400)
    workflow = str(uuid4())
    store.workflows.create("Density scan", {"format": "stk.workflow/1", "ui": {}, "steps": [
        {"id": "cases", "kind": "table", "ref": {"table": lammps.TABLE_ID}},
        {"id": "simulate", "kind": "simulation", "ref": {"template": "lammps/1"}, "inputs": {"rows": {"from": "cases.rows"}}}]},
        workflow_id=workflow, expected_revision=store.info()["revision"])
    h.bridge.workflow_executor.poll_seconds = 0.02
    return {"h": h, "store": store, "handle": handle, "client": client, "supervisor": supervisor, "api": api,
            "connection": connection, "rows": [first, second], "workflow": workflow, "program": program,
            "imported": imported, "tmp": tmp_path}


def test_import_reads_the_parameters_the_script_takes(scan):
    s = scan
    assert s["imported"]["parameters"] == ["pressure", "seed", "steps", "temperature"] and s["imported"]["units"] == "real"
    table = next(t for t in s["store"].snapshot()["tables"] if t["id"] == lammps.TABLE_ID)
    values = {row["id"]: {key: row["values"].get(field) for key, field in lammps.FIELD_IDS.items()} for row in table["records"]}
    first = values[s["rows"][0]]
    assert (first["script"], first["temperature"], first["steps"], first["seed"], first["timestep"]) == ("in.npt", 300, 100, 4928459, None)
    assert values[s["rows"][1]]["temperature"] == 400 and values[s["rows"][1]]["source"] == first["source"]
    assert set(first["source"]["bindings"]) == {"in.npt", "system.data"}
    assert "lammps/1" in remote_templates()


@pytest.mark.parametrize("extra, message", [("log.lammps", "clean case"), ("in.second", "Name the input script")])
def test_import_refuses_unclear_or_used_case_folders(scan, extra, message):
    s = scan
    source = write_case(s["tmp"] / ("case-" + extra))
    (source / extra).write_text("units real\n")
    revision = s["store"].info()["revision"]
    with pytest.raises(Exception, match=message):
        s["api"].lammps.import_case(source, expected_revision=revision)
    assert s["store"].info()["revision"] == revision


def test_a_script_stk_does_not_run_is_refused_at_import(scan):
    s = scan
    source = write_case(s["tmp"] / "bad", "units real\nshell date\nrun 10\n")
    revision = s["store"].info()["revision"]
    before = set((s["store"].directory / "inputs" / "lammps").iterdir())
    with pytest.raises(Exception, match="shell"):
        s["api"].lammps.import_case(source, expected_revision=revision)
    assert s["store"].info()["revision"] == revision and set((s["store"].directory / "inputs" / "lammps").iterdir()) == before


def prepare(s, rows=None):
    return s["h"].call("project.workflow_runs.prepare", {
        "handle": s["handle"], "workflow_id": s["workflow"], "rows": rows or s["rows"], "run_id": str(uuid4()),
        "expected_revision": s["store"].info()["revision"],
        "simulation": {"connection": s["connection"], "options": {"launcher": "none", "program": str(s["program"])}}})["run"]


def test_rows_run_as_a_workflow_step_on_the_runtime_and_are_collected(scan):
    s = scan
    run = prepare(s)
    frozen = run["parameters"]["simulate"]
    assert [frozen[row]["temperature"] for row in s["rows"]] == [300, 400]
    assert s["client"].tasks() == []  # preparing submits nothing
    s["h"].call("project.workflow_runs.start", {"handle": s["handle"], "run_id": run["id"]})
    done = settled(s, run["id"])
    assert done["complete"], done["tasks"]
    densities = {}
    for row in s["rows"]:
        produced = tasks(done)[("simulate", row)]["produced"]
        assert produced["directory"] == f"results/lammps/{produced['simulation_run_id']}"
        assert {"stk-lammps.json", "case/log.lammps", "case/final.data", "case/in.npt", "case/system.data",
                "case/stk-lammps-input.json", "case/fake-lammps.json"} == set(produced["files"])
        plan = s["store"].runs.get(produced["simulation_run_id"])["plan"]
        densities[plan["parameters"]["values"][lammps.FIELD_IDS["temperature"]]] = produced["result_record_id"]
    results = next(t for t in s["store"].snapshot()["tables"] if t["id"] == lammps.RESULT_TABLE_ID)
    by_id = {row["id"]: row["values"] for row in results["records"]}
    field = lammps.RESULT_FIELD_IDS
    assert by_id[densities[300]][field["density"]] == pytest.approx(1.40)
    assert by_id[densities[400]][field["density"]] == pytest.approx(1.36)
    assert by_id[densities[400]][field["temperature"]] == 400 and by_id[densities[400]][field["units"]] == "real"
    assert by_id[densities[400]][field["step"]] == 100 and by_id[densities[400]][field["thermo"]]["runs"] == 1
    assert len(s["client"].tasks()) == 2 and not s["h"].violations


def test_a_row_that_leaves_a_used_parameter_empty_is_refused_when_the_run_is_prepared(scan):
    s = scan
    cell(s["store"], s["rows"][0], "pressure", None)
    with pytest.raises(Exception, match="Row 1: The script uses pressure; set it in the row"):
        prepare(s, rows=[s["rows"][0]])
    cell(s["store"], s["rows"][0], "pressure", 1.0)
    cell(s["store"], s["rows"][0], "timestep", 2.0)
    with pytest.raises(Exception, match="does not use timestep"):
        prepare(s, rows=[s["rows"][0]])
    # Cloning keeps an incomplete row as it is, to be filled in afterwards.
    clone = s["api"].lammps.clone_case(s["rows"][0], expected_revision=s["store"].info()["revision"])["record_id"]
    assert clone and s["client"].tasks() == []
