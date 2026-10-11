"""Manual only: real LAMMPS scripts -> Runtime -> frozen results -> analysis.

Public 108-atom argon fixture, not PET or material-property validation. Run
with PYTHONPATH=tests, -p conftest and STK_LAMMPS=/path/to/lmp (see ../README.md).
Missing software fails instead of skipping. All projects live in pytest temp dirs.
"""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest

from suan.graph.catalog import load_preset
from suan.lammps import write_data
from suan.lammps.analysis import density_series
from suan.lammps.script import PARAMETERS
from suan.lammps.templates import template_text
from suan.project import ProjectStore
from suan.scripting import API
from suan.workflows import lammps
from test_bridge_workflow_muferro import settled, tasks
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_desktop_bridge_runtime import add_profile


def argon_case(folder, kind):
    folder.mkdir()
    atom_type = NS(epsilon=0.238, epsilon_14=0.238, rmin=3.405*2**(1/6)/2,
                   rmin_14=3.405*2**(1/6)/2, nbfix={})
    atoms = []
    for i in range(3):
        for j in range(3):
            for k in range(3):
                for x, y, z in ((0, 0, 0), (0, .5, .5), (.5, 0, .5), (.5, .5, 0)):
                    atoms.append(NS(atom_type=atom_type, mass=39.948, epsilon=0.238, sigma=3.405, charge=0.0,
                                    xx=(i+x)*5.4, xy=(j+y)*5.4, xz=(k+z)*5.4, exclusion_partners=[]))
    structure = NS(atoms=atoms, box=[16.2, 16.2, 16.2, 90, 90, 90], combining_rule="geometric")
    write_data(structure, folder / "system.data")
    (folder / "model.in").write_text("pair_style lj/cut 8.0\npair_modify mix geometric\nread_data system.data\n")
    (folder / ("in."+kind)).write_text(template_text(kind))
    return folder


@pytest.mark.parametrize("kind", ["tg", "modulus", "diffusion"])
def test_real_template_workflow_and_downstream_analysis(inproc, runtime, tmp_path, kind):
    program = os.environ.get("STK_LAMMPS")
    assert program and Path(program).is_file(), "Set STK_LAMMPS to a real LAMMPS executable"
    _, supervisor, _, _ = runtime
    h = inproc()
    connection = add_profile(h, runtime)
    store = ProjectStore.create(tmp_path / "project", "E1c "+kind)
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    api = API(lambda op, params: h.call(op, params))
    api._project_handle = handle
    folder = argon_case(tmp_path / "case", kind)
    row = api.lammps.import_case(folder, script="in."+kind, expected_revision=store.info()["revision"])["record_id"]
    values = {"temperature": 300 if kind == "diffusion" else 20, "steps": 1000,
              "equilibration_steps": 1000, "sample_interval": 10}
    if kind == "modulus":
        values["strain_rate"] = 2e-5
    store.apply([{"op": "set_cell", "table_id": lammps.TABLE_ID, "record_id": row,
                  "field_id": lammps.FIELD_IDS[key], "value": value} for key, value in values.items()],
                expected_revision=store.info()["revision"])
    if kind == "tg":
        graph = {"schema": "stk.graph/1", "catalog": {"stk": 1}, "parameters": [],
                 "nodes": [{"id": "thermo", "type": "stk.source.lammps_log@1",
                            "params": {"binding": "data", "path": "case/log.lammps"}}],
                 "outputs": {"table": "thermo.out"}}
        parameters, outputs = {}, ["table"]
    else:
        graph = load_preset("lammps-"+kind)
        parameters = {"path": "case/stress-strain.dat"} if kind == "modulus" else {
            "path": "case/msd.dat", "time_min": 100, "time_max": 1000}
        outputs = ["summary", "fit", "diagnostics", "plot"]
    analysis, workflow = str(uuid4()), str(uuid4())
    store.analyses.create("Read "+kind, {"format": "stk.analysis-document/1", "graph": graph,
                                        "parameters": parameters, "outputs": outputs},
                          analysis_id=analysis, expected_revision=store.info()["revision"])
    store.workflows.create("Run then analyze", {"format": "stk.workflow/1", "ui": {}, "steps": [
        {"id": "cases", "kind": "table", "ref": {"table": lammps.TABLE_ID}},
        {"id": "simulate", "kind": "simulation", "ref": {"template": "lammps/1"},
         "inputs": {"rows": {"from": "cases.rows"}}},
        {"id": "analyze", "kind": "analysis", "ref": {"analysis": analysis},
         "inputs": {"data": {"from": "simulate.files"}}}]}, workflow_id=workflow,
                           expected_revision=store.info()["revision"])
    h.bridge.workflow_executor.poll_seconds = 0.02
    run = h.call("project.workflow_runs.prepare", {"handle": handle, "workflow_id": workflow, "rows": [row],
        "run_id": str(uuid4()), "expected_revision": store.info()["revision"],
        "simulation": {"connection": connection, "options": {"program": program, "launcher": "none"}}})["run"]
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    done = settled({"h": h, "handle": handle, "supervisor": supervisor}, run["id"], timeout=900)
    assert done["complete"] and all(task["status"] == "succeeded" for task in done["tasks"]), done["tasks"]
    simulated = tasks(done)[("simulate", row)]["produced"]
    log = store.directory / simulated["directory"] / "case/log.lammps"
    log_text = log.read_text()
    point = density_series({kind: log_text})
    assert point.column("Density")[0] > 0
    analyzed = tasks(done)[("analyze", row)]["produced"]
    result = api.project.analysis_runs.result(analyzed["analysis_run_id"])["result"]
    assert not result.get("errors"), result
    if kind == "tg":
        assert len(result["outputs"]["table"]["columns"]["Density"]) == 101
        source = result["outputs"]["table"]["attrs"]["source"]["used"][0]
        print(kind, "density point", point.to_json())
    else:
        source = result["outputs"]["diagnostics"]["value"]["source"]["used"][0]
        print(kind, "finite-time smoke fit (not a validated property)", result["outputs"]["summary"]["columns"])
        assert result["outputs"]["fit"]["type"] == "table"
        assert result["outputs"]["plot"]["type"] == "plot"
    assert source["path"].startswith("case/")
    archived_source = store.directory / simulated["directory"] / source["path"]
    assert source["sha256"] == hashlib.sha256(archived_source.read_bytes()).hexdigest()
    assert not h.violations
    report_dir = os.environ.get("STK_E1C_REPORT_DIR")
    if report_dir:
        report = {"fixture": "public synthetic 108-atom FCC argon; finite-time path smoke, not property validation",
                  "kind": kind, "lammps_version": log_text.strip().splitlines()[0],
                  "parameters": {key: value for key, value in run["parameters"]["simulate"][row].items()
                                 if key in PARAMETERS and value is not None}, "analysis_parameters": parameters,
                  "density_point": point.to_json(), "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
                  "input_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                   for path in sorted(folder.iterdir())},
                  "outputs": {name: result["outputs"][name] for name in ("summary", "diagnostics")
                              if name in result["outputs"]}}
        destination = Path(report_dir)
        destination.mkdir(parents=True, exist_ok=True)
        with (destination / (kind + ".json")).open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
