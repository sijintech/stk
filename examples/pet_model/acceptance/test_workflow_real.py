"""Manual offline molecular-module -> frozen workflow -> LAMMPS acceptance.

Run with core Python, PYTHONPATH=.:tests, -p conftest and STK_MOLECULAR_PYTHON,
STK_PACKMOL, STK_LAMMPS pointing at actual registered-module binaries.
Software-path verification only; no equilibrated PET property claims.
"""
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from suan.modules import Modules
from suan.project import ProjectStore
from suan.scripting import API
from suan.workflows import lammps, pet
from test_bridge_workflow_runs import settled
from test_bridge_workflow_muferro import settled as settled_remote
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_desktop_bridge_runtime import add_profile


def test_real_modeling_rows_and_explicit_lammps_import(inproc, runtime, tmp_path, monkeypatch):
    programs = {key: Path(os.environ[key]).resolve(strict=True) for key in
                ("STK_MOLECULAR_PYTHON", "STK_PACKMOL", "STK_LAMMPS")}
    module_root = tmp_path / "modules"
    modules = Modules(module_root, extra_paths=[programs["STK_MOLECULAR_PYTHON"].parent,
                                               programs["STK_PACKMOL"].parent])
    modules.detect("molecular-modeling")
    modules.extra_paths = [programs["STK_PACKMOL"].parent]
    modules.detect("packmol")
    assert Path(modules.find_program("molecular-modeling", "python")).resolve() == programs["STK_MOLECULAR_PYTHON"]
    assert Path(modules.find_program("packmol", "packmol")).resolve() == programs["STK_PACKMOL"]
    monkeypatch.setenv("STK_MODULES_DIR", str(module_root))
    harness = inproc()
    store = ProjectStore.create(tmp_path / "project", "Public PET molecular acceptance")
    handle = harness.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    api = API(lambda operation, parameters: harness.call(operation, parameters))
    api._project_handle = handle
    rows = [{}, {"chain_length": 2, "chain_count": 1, "packing_density": 80.0}]
    made = api.lammps.create_pet_workflow(expected_revision=0, rows=rows)
    run = api.project.workflow_runs.prepare(made["workflow_id"], made["record_ids"], run_id=str(uuid4()),
                                            expected_revision=made["revision"])
    store.apply([{"op": "set_cell", "table_id": made["table_id"], "record_id": made["record_ids"][0],
                  "field_id": made["field_ids"]["seed"], "value": 99}], expected_revision=made["revision"])
    api.project.workflow_runs.start(run["id"])
    done = settled(harness, handle, run["id"], timeout=300)
    assert done["complete"] and done["counts"] == {"succeeded": 2}, done
    folders = []
    for task, expected_atoms in zip(done["tasks"], (546, 47)):
        produced = task["produced"]
        assert set(produced["files"]) == set(pet.OUTPUTS)
        folder = store.directory / produced["directory"]
        folders.append(folder)
        report = json.loads((folder / "pet-model.json").read_text())
        assert report["validation"]["atoms"] == expected_atoms
        assert report["parameters"]["seed"] == pet.DEFAULT_PARAMETERS["seed"]
        assert report["forcefield"]["charge_rounding_correction"]["effective_charge_e"] == -.565
        snapshot = store.snapshots.get(produced["snapshot_id"])["manifest"]["files"]
        expected = {record: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                    for name, record in produced["files"].items()}
        assert {entry["record_id"]: entry["sha256"] for entry in snapshot} == expected
    assert store.workflow_runs.get(run["id"])["plan_sha256"] == run["plan_sha256"]
    # Explicitly import the immutable generated case; do not imply automatic
    # chaining of a local model step into the existing remote LAMMPS template.
    row = api.lammps.import_case(folders[0], script="in.pet", expected_revision=store.info()["revision"])["record_id"]
    values = {"equilibration_steps": 20, "steps": 40, "sample_interval": 10, "timestep": .25}
    store.apply([{"op": "set_cell", "table_id": lammps.TABLE_ID, "record_id": row,
                  "field_id": lammps.FIELD_IDS[key], "value": value} for key, value in values.items()],
                expected_revision=store.info()["revision"])
    workflow = str(uuid4())
    written = store.workflows.create("PET preparation path smoke", {"format": "stk.workflow/1", "ui": {}, "steps": [
        {"id": "cases", "kind": "table", "ref": {"table": lammps.TABLE_ID}},
        {"id": "simulate", "kind": "simulation", "ref": {"template": "lammps/1"},
         "inputs": {"rows": {"from": "cases.rows"}}}]}, workflow_id=workflow,
        expected_revision=store.info()["revision"])
    connection = add_profile(harness, runtime)
    remote = harness.call("project.workflow_runs.prepare", {"handle": handle, "workflow_id": workflow,
        "rows": [row], "run_id": str(uuid4()), "expected_revision": written["revision"],
        "simulation": {"connection": connection, "options": {"program": str(programs["STK_LAMMPS"]), "launcher": "none"}}})["run"]
    harness.call("project.workflow_runs.start", {"handle": handle, "run_id": remote["id"]})
    complete = settled_remote({"h": harness, "handle": handle, "supervisor": runtime[1]}, remote["id"], timeout=300)
    assert complete["complete"] and complete["counts"] == {"succeeded": 1}, complete
    assert not harness.violations
    print("real PET rows 546/47 atoms; frozen eight artifacts; explicit Runtime/LAMMPS preparation smoke passed")
