"""Manual PET + oxygen study through the canonical desktop and Runtime services.

Use real registered molecular/Packmol/LAMMPS binaries, never a model endpoint.
The numerical outcomes, including rejected fits, are recorded without promoting
a finite software acceptance to a converged material-property certificate.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

import pytest

from suan.modules import Modules
from suan.scripting import API
from suan.lammps.pet_protocol import validate_recipe
from suan.lammps.structure import index_dump, read_data, read_dump_frame
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_desktop_bridge_runtime import add_profile


def verification_recipe():
    """A longer, reproducible software acceptance; durations are not convergence."""
    common = {"timestep": .25, "sample_interval": 1000}
    return validate_recipe({
        "relax": {**common, "warmup_steps": 8000, "compression_steps": 240000,
                  "equilibration_steps": 40000, "steps": 40000},
        "tg": {**common, "equilibration_steps": 8000, "steps": 20000},
        "modulus": {**common, "equilibration_steps": 8000, "steps": 20000},
        "diffusion": {**common, "group": "o2_com", "equilibration_steps": 20000, "steps": 200000},
    })


def project_directory(api, project):
    """Select this open handle, irrespective of the order of other open projects."""
    matches = [value for value in api.projects.list() if value["handle"] == project.handle]
    if len(matches) != 1:
        raise ValueError("The acceptance project handle is no longer uniquely open")
    return Path(matches[0]["directory"])


def test_real_pet_oxygen_study_and_reopen_offline(inproc, runtime, tmp_path, monkeypatch):
    programs = {key: Path(os.environ[key]).resolve(strict=True) for key in
                ("STK_MOLECULAR_PYTHON", "STK_PACKMOL", "STK_LAMMPS")}
    modules = Modules(tmp_path / "modules", extra_paths=[programs["STK_MOLECULAR_PYTHON"].parent])
    modules.detect("molecular-modeling")
    modules.extra_paths = [programs["STK_PACKMOL"].parent]
    modules.detect("packmol")
    monkeypatch.setenv("STK_MODULES_DIR", str(modules.root))
    recipe_path = os.environ.get("STK_PET_ACCEPTANCE_RECIPE")
    recipe = validate_recipe(json.loads(Path(recipe_path).read_text())) if recipe_path else verification_recipe()
    assert recipe["diffusion"]["group"] == "o2_com", "Full gas acceptance needs oxygen, not polymer self-diffusion"
    timeout = int(os.environ.get("STK_PET_ACCEPTANCE_TIMEOUT", "7200"))
    h = inproc()
    api = API(h.call)
    project = api.projects.create(tmp_path / "project", "Public PET oxygen study acceptance")
    api._project_handle = project.handle
    connection = add_profile(h, runtime)
    study = api.lammps.create_pet_study(recipe, connection=connection, expected_revision=0,
        options={"program": str(programs["STK_LAMMPS"]), "launcher": "none"}, wait_seconds=timeout)
    assert study["status"] == "prepared" and not study["objects"]
    assert runtime[0].tasks() == []  # preparing and reading cannot execute a solver
    api.lammps.start_pet_study(study["study_id"], expected_revision=project.snapshot()["project"]["revision"])
    deadline, last = time.monotonic() + timeout, None
    while time.monotonic() < deadline:
        runtime[1].tick()
        anchor = project.workflow_runs.get(study["run_id"])
        if anchor["status"] == "stopped" and not h.bridge.workflow_executor.active(
                h.bridge.projects._stores[project.handle], study["run_id"]):
            break
        stages = api.lammps.get_pet_study(study["study_id"])["stages"]
        summary = [(key, value["status"]) for key, value in stages.items()]
        if summary != last:
            print("PET stage journals:", summary, flush=True)
            last = summary
        time.sleep(.2)
    else:
        pytest.fail("Real PET study exceeded the explicit acceptance wait budget")
    verify_completed_study(api, project, h, runtime, study, anchor, tmp_path, monkeypatch)


def verify_completed_study(api, project, h, runtime, study, anchor, tmp_path, monkeypatch):
    """Shared actual-MD acceptance after either a fresh run or explicit recovery."""
    recipe = study["recipe"]
    assert anchor["complete"] and anchor["counts"] == {"succeeded": 1}, anchor["tasks"]
    result = api.lammps.get_pet_study(study["study_id"])
    expected_solver_stages = 3 + len(recipe["tg"]["temperatures"])
    assert len(runtime[0].tasks()) == expected_solver_stages
    produced = anchor["tasks"][0]["produced"]
    report_file = project.snapshots.resolve(produced["snapshot_id"], produced["files"]["pet-study.json"])
    report = json.loads(Path(report_file["path"]).read_text())
    assert report["software_complete"] and report["material_validation"] is False
    assert report["diffusion_scope"] == "O2 tracer COM"
    frames, densities = {}, {}
    for key, value in result["stages"].items():
        if key.startswith("analysis:") or key == "model":
            continue
        assert value["complete"] and value["counts"] == {"succeeded": 1}
        files = value["tasks"][0]["produced"]
        resolved = {name: project.snapshots.resolve(files["snapshot_id"], identity)
                    for name, identity in files["files"].items()}
        for item in resolved.values():
            assert hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() == item["sha256"]
        topology = read_data(resolved["case/state.data"]["path"])
        viewed = api.lammps.view(files["simulation_run_id"], project=project)
        trajectory = Path(viewed["directory"]) / "trajectory.dump"
        recorded = next(item for item in viewed["files"] if item["path"].endswith("/case/trajectory.dump"))
        assert hashlib.sha256(trajectory.read_bytes()).hexdigest() == recorded["sha256"]
        indexed = index_dump(trajectory, topology)
        frame = read_dump_frame(trajectory, topology, index=indexed)
        stage = "tg" if key.startswith("property:tg:") else key.removeprefix("property:")
        assert frame.has_unwrapped
        assert indexed.frames[0].step == 0 and indexed.frames[-1].step == recipe[stage]["steps"]
        assert 2 <= len(indexed.frames) <= 128
        expected_atoms = (22 * recipe["model"]["chain_length"] + 3) * recipe["model"]["chain_count"]
        if stage == "diffusion":
            expected_atoms += 2 * recipe["diffusion"]["gas_count"]
            assert "case/gas-model.json" in resolved and "case/oxygen.mol" in resolved
        assert len(topology.atoms) == expected_atoms == len(frame.atoms)
        frames[key] = len(indexed.frames)
        status = json.loads(Path(resolved["stk-lammps.json"]["path"]).read_text())
        assert status["state"] == "succeeded" and status["verification"]["status"] == "passed"
        densities[key] = status["qoi"]["density"]
    archived = {}
    for kind in ("tg", "modulus", "diffusion"):
        run = project.analysis_runs.result(result["objects"]["analysis:" + kind]["run_id"])
        assert run["run"]["status"] in {"succeeded", "failed"}
        archived[kind] = {"status": run["run"]["status"], "errors": run["result"].get("errors", [])}
    tasks_before = {task["id"] for task in runtime[0].tasks()}
    api.lammps.start_pet_study(study["study_id"], expected_revision=project.snapshot()["project"]["revision"])
    assert tasks_before == {task["id"] for task in runtime[0].tasks()}
    current_directory = project_directory(api, project)
    project.close()
    moved = tmp_path / "relocated-project"
    shutil.move(current_directory, moved)
    project = api.projects.open(moved)
    api._project_handle = project.handle
    original_call = api._call

    def offline(operation, params):
        assert not operation.startswith("runtime.") and operation != "project.runs.refresh"
        return original_call(operation, params)

    monkeypatch.setattr(api, "_call", offline)
    reopened = api.lammps.get_pet_study(study["study_id"])
    assert reopened["complete"] and reopened["objects"] == result["objects"]
    for kind in ("tg", "modulus", "diffusion"):
        project.analysis_runs.result(reopened["objects"]["analysis:" + kind]["run_id"])
    assert not h.violations
    from evidence import verify_saved_evidence
    numerical_evidence = verify_saved_evidence(project, reopened, lammps=api.lammps)
    print("PET full-path evidence:", json.dumps({"study_id": study["study_id"],
        "recipe": recipe, "solver_stages": expected_solver_stages, "density_g_cm3": densities,
        "trajectory_frames": frames, "analysis": archived, "software_complete": True,
        "material_validation": False, "independent_numerical_checks": numerical_evidence}, ensure_ascii=False), flush=True)


@pytest.mark.skipif(not os.environ.get("STK_PET_STUDY_PROJECT"), reason="Explicit saved real PET acceptance project required")
def test_existing_real_project_evidence_offline(inproc, monkeypatch):
    """Recheck a completed acceptance without rerunning any molecular dynamics."""
    from evidence import verify_saved_evidence
    from suan.workflows.pet_study import TABLE_ID
    h = inproc()
    api = API(h.call)
    project = api.projects.open(Path(os.environ["STK_PET_STUDY_PROJECT"]))
    api._project_handle = project.handle
    original = api._call

    def offline(operation, params):
        assert not operation.startswith("runtime.") and operation != "project.runs.refresh"
        return original(operation, params)

    monkeypatch.setattr(api, "_call", offline)
    table = next(table for table in project.snapshot()["tables"] if table["id"] == TABLE_ID)
    assert len(table["records"]) == 1
    result = api.lammps.get_pet_study(table["records"][0]["id"])
    print("Independent saved PET evidence:", verify_saved_evidence(project, result, lammps=api.lammps), flush=True)
