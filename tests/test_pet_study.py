"""Persistent orchestration through real project journals and a synthetic solver.

The model and solver fixtures are deliberately synthetic. Scientific PET
validation uses the independent manual acceptance, not these transport tests.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

import pytest

from lammps_fake import PROGRAM
from suan.project import ProjectStore
from suan.scripting import API
from suan.workflows import pet
from suan.workflows.pet_study import FIELD_IDS, LINK_FIELD_IDS, LINK_TABLE_ID, TABLE_ID, PetStudy, _id
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_desktop_bridge_runtime import add_profile
from test_bridge_workflow_runs import settled


@pytest.fixture
def study(inproc, runtime, tmp_path, monkeypatch):
    import sys
    from suan.lammps.pet import forcefield_text, profile
    from suan.lammps.pet_protocol import default_recipe
    h = inproc()
    api = API(h.call)
    project = api.projects.create(tmp_path / "project", "Synthetic PET study transport")
    api._project_handle = project.handle
    h.bridge.workflow_executor.poll_seconds = .02
    connection = add_profile(h, runtime)
    program = tmp_path / "lmp"
    script = PROGRAM.replace('pathlib.Path(words[1]).write_text("fake LAMMPS data file\\n")',
        'state=pathlib.Path("input-state.data").read_text()\n'
        '        if "Velocities" not in state:\n'
        '            count=int(re.search(r"(\\d+) atoms",state).group(1))\n'
        '            state+="\\nVelocities\\n\\n"+"".join(f"{{i}} 0 0 0\\n" for i in range(1,count+1))\n'
        '        pathlib.Path(words[1]).write_text(state)')
    script = script.format(python=sys.executable)
    script += '''
if script == "in.modulus":
    pathlib.Path("stress-strain.dat").write_text("Step Strain Stress\\n" + "".join(f"{i} {i*.005} {0.1+2.5*i*.005}\\n" for i in range(9)))
if script == "in.diffusion":
    pathlib.Path("msd.dat").write_text("Step Time MSD\\n" + "".join(f"{i} {i*100} {0.2+0.006*i*100}\\n" for i in range(1001)))
'''
    program.write_text(script)
    program.chmod(0o755)
    calls = []

    def build(parameters, directory, *, cancel=None):
        calls.append(deepcopy(parameters))
        directory = Path(directory)
        directory.mkdir()
        n, count = parameters["chain_length"], parameters["chain_count"]
        atoms = (22*n+3)*count
        data = ("Synthetic transport-only full data\n\n" + f"{atoms} atoms\n0 bonds\n0 angles\n0 dihedrals\n0 impropers\n\n"
                + "1 atom types\n\n0 100 xlo xhi\n0 100 ylo yhi\n0 100 zlo zhi\n\nMasses\n\n1 12\n\n"
                + "Pair Coeffs\n\n1 0.1 3.4\n\nAtoms # full\n\n"
                + "".join(f"{i} 1 1 0 {i%10+1} {(i//10)%10+1} {i//100+1}\n" for i in range(1, atoms+1)))
        for name in pet.OUTPUTS:
            if name != "pet-model.json":
                (directory / name).write_text("# synthetic transport fixture\n")
        (directory / "pet.data").write_text(data)
        (directory / "model.in").write_text("pair_style lj/cut 12\npair_modify mix geometric\nread_data pet.data\n")
        (directory / "forcefield.xml").write_text(forcefield_text())
        definition = profile()
        report = {"format": "stk.pet-model/1", "profile_id": "stk.pet.opls-mk2022/1", "parameters": parameters,
                  "forcefield": definition, "profile_canonical_sha256": hashlib.sha256(json.dumps(definition,
                    sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest(),
                  "forcefield_xml_sha256": hashlib.sha256(forcefield_text().encode()).hexdigest(),
                  "validation": {"atoms": atoms, "chain_count": count,
                    "formula_per_chain": {"C": 10*n, "H": 8*n+2, "O": 4*n+1}, "chain_charge_e": [0.0]*count},
                  "files": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                            for name in pet.OUTPUTS if name != "pet-model.json"}}
        (directory / "pet-model.json").write_text(json.dumps(report))
    monkeypatch.setattr(pet, "model_pet", build)
    recipe = default_recipe("pilot")
    recipe["model"] = {"chain_length": 2, "chain_count": 1, "packing_density": 80., "seed": 42}
    recipe["tg"]["temperatures"] = [600., 500., 400., 350., 300., 250.]
    return {"h": h, "api": api, "p": project, "service": PetStudy(api), "connection": connection,
            "options": {"program": str(program), "launcher": "none"}, "recipe": recipe, "calls": calls,
            "runtime": runtime, "tmp": tmp_path}


def revision(s):
    return s["p"].snapshot()["project"]["revision"]


def create(s, **kwargs):
    return s["service"].create(s["recipe"], connection=s["connection"], options=s["options"],
                               expected_revision=revision(s), **kwargs)


def done(s, identity, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        s["runtime"][1].tick()
        run = s["p"].workflow_runs.get(identity)
        if run["status"] == "stopped" and not s["h"].bridge.workflow_executor.active(
                s["h"].bridge.projects._stores[s["p"].handle], identity):
            return run
        time.sleep(.02)
    pytest.fail("PET study did not settle")


def test_create_and_reads_do_not_execute_and_pin_recipe_and_runtime_intent(study):
    s = study
    made = create(s)
    assert made["status"] == "prepared" and not made["complete"] and made["objects"] == {}
    assert s["calls"] == []
    assert made["simulation"]["connection"] == s["connection"]
    assert len(made["simulation"]["connection_identity"]) == 16
    before = revision(s)
    assert s["service"].status(made["study_id"])["recipe"] == made["recipe"]
    assert s["service"].advance(made["study_id"], expected_revision=before)["status"] == "prepared"
    assert revision(s) == before and s["calls"] == []
    assert create(s, study_id=made["study_id"])["run_id"] == made["run_id"]


@pytest.mark.parametrize("bad", [[], False, 0, "x"])
def test_invalid_recipe_and_options_do_not_disappear_into_defaults(study, bad):
    s = study
    with pytest.raises((ValueError, TypeError)):
        s["service"].create(bad, connection=s["connection"], options=s["options"], expected_revision=0)
    with pytest.raises((ValueError, TypeError)):
        s["service"].create(s["recipe"], connection=s["connection"], options=bad, expected_revision=0)
    assert revision(s) == 0


def test_reserved_options_and_revision_are_rejected_before_creation(study):
    s = study
    with pytest.raises(ValueError, match="resource options"):
        s["service"].create(s["recipe"], connection=s["connection"], options={"inputs": []}, expected_revision=0)
    with pytest.raises(ValueError, match="Project changed"):
        s["service"].create(s["recipe"], connection=s["connection"], options=s["options"], expected_revision=1)
    assert revision(s) == 0 and s["calls"] == []


def test_oxygen_orientation_seed_reserves_the_frozen_mpi_rank_offsets(study):
    s = study
    recipe = deepcopy(s["recipe"])
    recipe["diffusion"].update(group="o2_com", gas_seed=900000000)
    with pytest.raises(ValueError, match="MPI rank offsets"):
        s["service"].create(recipe, connection=s["connection"], options={**s["options"], "ranks": 2}, expected_revision=0)
    assert revision(s) == 0 and s["calls"] == []


def test_full_study_uses_frozen_handoffs_and_archives_rejected_fit_without_claiming_material_validation(study):
    s = study
    made = create(s)
    parameter_row = deepcopy(next(table for table in s["p"].snapshot()["tables"] if table["id"] == TABLE_ID)["records"])
    s["service"].start(made["study_id"], expected_revision=revision(s))
    run = done(s, made["run_id"])
    assert run["complete"], run["tasks"]
    result = s["service"].get(made["study_id"])
    assert len(s["calls"]) == 1
    assert all(stage["complete"] for key, stage in result["stages"].items() if not key.startswith("analysis:"))
    assert result["stages"]["analysis:tg"]["status"] == "failed"  # a single straight density line has no Tg
    assert result["stages"]["analysis:modulus"]["status"] == "succeeded"
    assert result["stages"]["analysis:diffusion"]["status"] == "succeeded"
    produced = run["tasks"][0]["produced"]
    frozen = s["p"].snapshots.resolve(produced["snapshot_id"], produced["files"]["pet-study.json"])
    report = json.loads(Path(frozen["path"]).read_text())
    assert report["software_complete"] and not report["fits_resolved"] and report["material_validation"] is False
    assert report["analyses"]["tg"]["graph_errors"]
    assert next(table for table in s["p"].snapshot()["tables"] if table["id"] == TABLE_ID)["records"] == parameter_row
    for key, item in result["objects"].items():
        if key != "relax" and not key.startswith("property:"):
            continue
        child = s["p"].workflow_runs.get(item["run_id"])
        snapshot = child["tasks"][0]["produced"]
        record = snapshot["files"]["case/pet-stage.json"]
        receipt = json.loads(Path(s["p"].snapshots.resolve(snapshot["snapshot_id"], record)["path"]).read_text())
        initial = snapshot["files"]["case/input-state.data"]
        initial_sha = s["p"].snapshots.resolve(snapshot["snapshot_id"], initial)["sha256"]
        assert receipt["input_state_sha256"] == initial_sha
    completed_ids = {key: item["run_id"] for key, item in result["objects"].items() if "run_id" in item}
    s["service"].start(made["study_id"], expected_revision=revision(s))
    assert {key: item["run_id"] for key, item in s["service"].get(made["study_id"])["objects"].items()
            if "run_id" in item} == completed_ids
    assert len(s["calls"]) == 1
    # Matching bytes alone do not authorize another study's aggregation receipt.
    original_objects = deepcopy(result["objects"])
    from suan.workflows.pet_study import _frozen_files
    raw = _frozen_files(s["p"], original_objects["tg_inputs"])
    receipt = json.loads(raw["tg-series.json"])
    receipt["study_id"] = str(uuid4())
    raw["tg-series.json"] = json.dumps(receipt).encode()
    foreign = s["tmp"] / "foreign-series"
    foreign.mkdir()
    paths = []
    for name, value in raw.items():
        path = foreign / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        paths.append(path)
    indexed = s["p"].files.index(paths, expected_revision=revision(s))
    captured = s["p"].snapshots.capture(indexed["record_ids"], expected_revision=indexed["revision"])
    altered = deepcopy(original_objects)
    altered["tg_inputs"] = {"snapshot_id": captured["snapshot"]["id"], "files": dict(zip(raw, indexed["record_ids"]))}
    s["service"]._save(s["p"], made["study_id"], made["run_id"], altered)
    with pytest.raises(ValueError, match="different study"):
        s["service"].get(made["study_id"])
    # A self-consistent edited CSV hash is still rejected against actual log
    # means; changing a receipt cannot make fabricated human exports valid.
    receipt["study_id"] = made["study_id"]
    raw["density-temperature.csv"] += b"999,9,forged,1\n"
    receipt["density_csv_sha256"] = hashlib.sha256(raw["density-temperature.csv"]).hexdigest()
    raw["tg-series.json"] = json.dumps(receipt).encode()
    for name in ("density-temperature.csv", "tg-series.json"):
        (foreign / name).write_bytes(raw[name])
    indexed = s["p"].files.index(paths, expected_revision=revision(s))
    captured = s["p"].snapshots.capture(indexed["record_ids"], expected_revision=indexed["revision"])
    altered["tg_inputs"] = {"snapshot_id": captured["snapshot"]["id"], "files": dict(zip(raw, indexed["record_ids"]))}
    s["service"]._save(s["p"], made["study_id"], made["run_id"], altered)
    with pytest.raises(ValueError, match="different study"):
        s["service"].get(made["study_id"])
    s["service"]._save(s["p"], made["study_id"], made["run_id"], original_objects)
    # Moving the whole project preserves frozen inputs and archives. Reading
    # and a redundant start of a complete study cannot reconnect or execute.
    import shutil
    root = Path(s["api"].projects.list()[0]["directory"])
    s["p"].close()
    relocated = s["tmp"] / "relocated"
    shutil.move(root, relocated)
    s["p"] = s["api"].projects.open(relocated)
    s["api"]._project_handle = s["p"].handle
    s["api"].runtime = lambda *args, **kwargs: pytest.fail("offline status must not contact Runtime")
    reopened = s["service"].get(made["study_id"])
    assert reopened["complete"] and reopened["objects"] == result["objects"]
    for kind in ("tg", "modulus", "diffusion"):
        archived = s["p"].analysis_runs.result(reopened["objects"]["analysis:" + kind]["run_id"])
        assert archived["run"]["status"] == reopened["stages"]["analysis:" + kind]["status"]
    s["service"].start(made["study_id"], expected_revision=revision(s))
    assert len(s["calls"]) == 1


def test_changed_recipe_stale_revision_and_other_project_cannot_start_existing_study(study):
    s = study
    made = create(s)
    before = revision(s)
    modified = deepcopy(made["recipe"])
    modified["model"]["seed"] += 1
    s["p"].apply([{"op": "set_cell", "table_id": TABLE_ID, "record_id": made["study_id"],
                   "field_id": FIELD_IDS["recipe"], "value": modified}], expected_revision=before)
    with pytest.raises(ValueError, match="Project changed"):
        s["service"].start(made["study_id"], expected_revision=before)
    assert s["service"].get(made["study_id"])["definition_changed"]
    with pytest.raises(ValueError, match="recipe changed"):
        s["service"].start(made["study_id"], expected_revision=revision(s))
    other = s["api"].projects.create(s["tmp"] / "other", "Other")
    s["api"]._project_handle = other.handle
    with pytest.raises(ValueError, match="Select a PET study"):
        s["service"].get(made["study_id"])
    assert s["calls"] == []


def test_interrupted_creation_recovers_explicitly_without_overwriting_recipe_or_runtime_intent(study, monkeypatch):
    from suan.scripting import ProjectWorkflowRuns
    s = study
    identity = str(uuid4())
    original = ProjectWorkflowRuns.prepare

    def fail(*args, **kwargs):
        raise ValueError("synthetic Runtime preparation failure")

    monkeypatch.setattr(ProjectWorkflowRuns, "prepare", fail)
    with pytest.raises(ValueError, match="preparation failure"):
        create(s, study_id=identity)
    before = revision(s)
    state = s["service"].get(identity)
    assert state["status"] == "incomplete" and state["run_id"] is None
    assert s["calls"] == [] and revision(s) == before
    with pytest.raises(ValueError, match="different recipe or Runtime"):
        s["service"].create(s["recipe"], study_id=identity, connection="runtime:another",
                             options=s["options"], expected_revision=before)
    monkeypatch.setattr(ProjectWorkflowRuns, "prepare", original)
    recovered = s["service"].recover(identity, expected_revision=revision(s))
    assert recovered["status"] == "prepared" and recovered["objects"] == {} and s["calls"] == []
    assert create(s, study_id=identity)["run_id"] == recovered["run_id"]


def test_partial_creation_refuses_edited_workflow_and_foreign_child_links(study, monkeypatch):
    from suan.scripting import ProjectWorkflowRuns
    s = study
    identity = str(uuid4())
    original = ProjectWorkflowRuns.prepare
    monkeypatch.setattr(ProjectWorkflowRuns, "prepare", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("stop")))
    with pytest.raises(ValueError, match="stop"):
        create(s, study_id=identity)
    workflow = _id(identity, "workflow")
    document = s["p"].workflows.get(workflow)["workflow"]["document"]
    document["steps"][1]["label"] = "Edited after failure"
    s["p"].workflows.update(workflow, "Edited", document, expected_revision=revision(s))
    monkeypatch.setattr(ProjectWorkflowRuns, "prepare", original)
    with pytest.raises(ValueError, match="child workflow changed"):
        s["service"].recover(identity, expected_revision=revision(s))
    made = create(s)
    foreign = str(uuid4())
    links = {"model": {"workflow_id": _id(foreign, "model:workflow"), "run_id": _id(foreign, "model:run"),
                       "record_id": _id(foreign, "model:row")}}
    s["p"].apply([{"op": "set_cell", "table_id": LINK_TABLE_ID, "record_id": _id(made["study_id"], "links"),
                   "field_id": LINK_FIELD_IDS["objects"], "value": links}], expected_revision=revision(s))
    with pytest.raises(ValueError, match="different study"):
        s["service"].get(made["study_id"])
    assert s["calls"] == []


def test_explicit_cancel_reaches_the_existing_model_workflow_without_dispatching_runtime(study, monkeypatch):
    import threading
    s = study
    entered = threading.Event()

    def slow(parameters, directory, *, cancel):
        entered.set()
        assert cancel.wait(10), "cancellation must reach the model step"
        raise pet.ModelingCancelled("synthetic cancellation")

    monkeypatch.setattr(pet, "model_pet", slow)
    made = create(s)
    s["service"].start(made["study_id"], expected_revision=revision(s))
    assert entered.wait(5)
    s["service"].cancel(made["study_id"], expected_revision=revision(s))
    run = done(s, made["run_id"])
    assert not run["complete"] and run["counts"] == {"cancelled": 1}
    result = s["service"].get(made["study_id"])
    assert result["stages"]["model"]["counts"] == {"cancelled": 1}
    assert "relax" not in result["objects"]


def test_snapshot_handoff_checks_frozen_objects_and_never_reads_mutable_working_paths(study):
    from suan.workflows.pet_study import _frozen_files
    s = study
    source = s["tmp"] / "source.data"
    source.write_bytes(b"immutable initial state\n")
    indexed = s["p"].files.index([source], expected_revision=revision(s))
    captured = s["p"].snapshots.capture(indexed["record_ids"], expected_revision=indexed["revision"])
    mapping = {"snapshot_id": captured["snapshot"]["id"], "files": {"input-state.data": indexed["record_ids"][0]}}
    source.write_bytes(b"changed working input\n")
    assert _frozen_files(s["p"], mapping) == {"input-state.data": b"immutable initial state\n"}
    frozen = s["p"].snapshots.resolve(mapping["snapshot_id"], indexed["record_ids"][0])
    Path(frozen["path"]).write_bytes(b"corrupted frozen object\n")
    with pytest.raises(Exception) as error:
        _frozen_files(s["p"], mapping)
    assert "checksum" in str(error.value).lower() or "changed" in str(error.value).lower()


def test_close_recover_and_restart_adopt_the_same_accepted_runtime_task(study):
    s = study
    (s["tmp"] / "lmp.json").write_text(json.dumps({"mode": "slow"}))
    made = create(s)
    s["service"].start(made["study_id"], expected_revision=revision(s))
    client, supervisor, _, _ = s["runtime"]

    def wait(predicate, seconds=30):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            supervisor.tick()
            result = s["service"].get(made["study_id"])
            if predicate(result):
                return result
            time.sleep(.02)
        pytest.fail("PET accepted-task lifecycle did not advance")

    running = wait(lambda result: "relax" in result["stages"]
        and (result["stages"]["relax"]["tasks"][0].get("progress") or {}).get("task_id")
        and client.task(result["stages"]["relax"]["tasks"][0]["progress"]["task_id"])["state"] == "running")
    accepted = running["stages"]["relax"]["tasks"][0]["progress"]["task_id"]
    simulation_run = running["stages"]["relax"]["tasks"][0]["progress"]["simulation_run_id"]
    root = Path(s["api"].projects.list()[0]["directory"])
    s["p"].close()
    time.sleep(.3)
    assert client.task(accepted)["state"] == "running"
    s["p"] = s["api"].projects.open(root)
    s["api"]._project_handle = s["p"].handle
    reopened = wait(lambda result: result["status"] == "stopped")
    assert not reopened["complete"]
    assert len(s["calls"]) == 1
    s["service"].recover(made["study_id"], expected_revision=revision(s))
    s["service"].start(made["study_id"], expected_revision=revision(s))
    adopted = wait(lambda result: result["stages"]["relax"]["tasks"][0]["attempt"] == 2
        and (result["stages"]["relax"]["tasks"][0].get("progress") or {}).get("simulation_run_id") == simulation_run)
    assert s["p"].runs.get(simulation_run)["status"]["task"]["id"] == accepted
    assert len(client.tasks()) == 1 and len(s["calls"]) == 1
    assert adopted["stages"]["model"]["tasks"][0]["attempt"] == 1
    s["service"].cancel(made["study_id"], expected_revision=revision(s))
    stopped = done(s, made["run_id"])
    assert not stopped["complete"]
    # The explicit cancel, unlike closing the project, reaches Runtime.
    deadline = time.monotonic() + 10
    while client.task(accepted)["state"] != "cancelled" and time.monotonic() < deadline:
        supervisor.tick()
        time.sleep(.02)
    assert client.task(accepted)["state"] == "cancelled"


def toy_state(gas=False):
    """A tiny transport topology, explicitly not a chemically valid PET model."""
    from suan.lammps.pet_protocol import oxygen_profile
    p = oxygen_profile()
    atoms = "".join(f"{i} 1 1 0 {i+1} 1 1\n" for i in range(1, 4))
    masses, pairs, bonded, bonds = "1 12\n", "1 0.1 3.4\n", "", ""
    if gas:
        masses += "2 15.9994\n"
        pairs += f"2 {p['LJ_epsilon_kcal_mol']:.17g} {p['lammps_LJ_sigma_A']:.17g}\n"
        bonded = f"\nBond Coeffs\n\n1 {p['lammps_harmonic_K_kcal_mol_A2']:.17g} {p['bond_length_A']:.17g}\n"
        atoms += "4 2 2 0 10 1 1\n5 2 2 0 11 1 1\n6 3 2 0 12 1 1\n7 3 2 0 13 1 1\n"
        bonds = "\nBonds\n\n1 1 4 5\n2 1 6 7\n"
    return (f"Toy state for handoff tests\n\n{7 if gas else 3} atoms\n{2 if gas else 0} bonds\n"
            f"0 angles\n0 dihedrals\n0 impropers\n\n{2 if gas else 1} atom types\n{1 if gas else 0} bond types\n"
            "0 angle types\n0 dihedral types\n0 improper types\n\n0 30 xlo xhi\n0 30 ylo yhi\n0 30 zlo zhi\n"
            f"\nMasses\n\n{masses}\nPair Coeffs\n\n{pairs}{bonded}\nAtoms # full\n\n{atoms}{bonds}"
            "\nVelocities\n\n" + "".join(f"{i} 0 0 0\n" for i in range(1, (7 if gas else 3) + 1))).encode()


@pytest.mark.parametrize("change,message", [
    (lambda raw: raw.replace(b"1 1 1 0 2", b"1 1 1 .001 2"), "charge"),
    (lambda raw: raw.replace(b"1 12\n", b"1 13\n"), "mass"),
    (lambda raw: raw.replace(b"1 0.1 3.4", b"1 0.2 3.4"), "coefficients"),
    (lambda raw: raw.replace(b"3 0 0 0\n", b""), "velocities"),
])
def test_handoff_rejects_lost_identity_parameters_and_velocities(change, message):
    from suan.lammps.pet_protocol import default_recipe
    from suan.workflows.pet_study import _validate_state
    initial = toy_state()
    assert _validate_state(initial, initial, default_recipe(), "tg")["polymer_identity_and_forcefield"] == "preserved"
    with pytest.raises(ValueError, match=message):
        _validate_state(initial, change(initial), default_recipe(), "tg")


def test_oxygen_state_validates_actual_new_coefficients_and_one_bond_per_molecule():
    from suan.lammps.pet_protocol import validate_recipe
    from suan.workflows.pet_study import _validate_state
    recipe = validate_recipe({"diffusion": {"group": "o2_com", "gas_count": 2}})
    initial, final = toy_state(), toy_state(gas=True)
    audit = _validate_state(initial, final, recipe, "diffusion")
    assert audit["atoms_after"] == 7 and audit["added_o2_molecules"] == 2
    for changed in (final.replace(b"0.1047", b"0.2047"), final.replace(b"820.2", b"821.2"),
                    final.replace(b"2 1 6 7", b"2 1 5 4"), final.replace(b"6 3 2", b"6 4 2")):
        with pytest.raises(ValueError):
            _validate_state(initial, changed, recipe, "diffusion")


def serialized_dihedral_state():
    """Exact values observed in the real 546-atom PET write_data handoff."""
    source = toy_state().replace(b"0 dihedral types", b"14 dihedral types")
    source = source.replace(b"Atoms # full", b"Dihedral Coeffs # opls\n\n"
        b"13 4.318996175908222 -0 -0 -0\n"
        b"14 2.390057361134623e-06 -0 0.4679995219885277 -0\n\nAtoms # full")
    written = source.replace(b"4.318996175908222", b"4.319").replace(
        b"2.390057361134623e-06", b"2.39006e-06").replace(b"0.4679995219885277", b"0.468")
    return source, written


def test_lammps_six_significant_digit_serialization_is_explicit_and_not_cumulative():
    from suan.lammps.pet_protocol import default_recipe
    from suan.workflows.pet_study import _validate_state
    original, written = serialized_dihedral_state()
    audit = _validate_state(original, written, default_recipe(), "relax", forcefield_bytes=original)
    changed = {(item["type"], item["component"]): item for item in audit["coefficient_rounding"]}
    assert set(changed) == {(13, 0), (14, 0), (14, 2)}
    assert changed[13, 0]["reference"] == 4.318996175908222 and changed[13, 0]["actual"] == 4.319
    assert all(item["accepted_by"] == "lammps_write_data_6g" for item in changed.values())
    next_audit = _validate_state(written, written, default_recipe(), "tg", forcefield_bytes=original)
    assert next_audit["input_coefficient_rounding"] == next_audit["coefficient_rounding"]
    assert next_audit["coefficient_reference_sha256"] == hashlib.sha256(original).hexdigest()
    # A full-precision state is valid too, after the original coefficients were restored.
    assert _validate_state(written, original, default_recipe(), "tg", forcefield_bytes=original)["coefficient_rounding"] == []
    for altered in (written.replace(b"4.319 ", b"4.31901 "), written.replace(b"0.468 ", b"0.46801 "),
                    written.replace(b"4.319 ", b"4.319000000001 "),
                    written.replace(b"2.39006e-06", b"2.49e-06"),
                    written.replace(b"2.39006e-06", b"2.39007e-06"),
                    written.replace(b"13 4.319", b"1 4.319")):
        with pytest.raises(ValueError, match="coefficients|coefficient records"):
            _validate_state(original, altered, default_recipe(), "tg", forcefield_bytes=original)
    with pytest.raises(ValueError, match="input state changed"):
        _validate_state(written.replace(b"4.319 ", b"4.31901 "), written, default_recipe(), "tg", forcefield_bytes=original)
    extra_type = written.replace(b"1 atom types", b"2 atom types").replace(b"1 12\n", b"1 12\n2 12\n")
    with pytest.raises(ValueError, match="type counts differ"):
        _validate_state(extra_type, extra_type, default_recipe(), "tg", forcefield_bytes=original)


def test_oxygen_output_rounding_is_limited_to_published_coefficient_representation():
    from suan.lammps.pet_protocol import oxygen_profile, validate_recipe
    from suan.workflows.pet_study import _validate_state
    recipe = validate_recipe({"diffusion": {"group": "o2_com", "gas_count": 2}})
    initial, final = toy_state(), toy_state(gas=True)
    sigma = format(oxygen_profile()["lammps_LJ_sigma_A"], ".17g").encode()
    rounded = final.replace(sigma, format(oxygen_profile()["lammps_LJ_sigma_A"], ".6g").encode())
    audit = _validate_state(initial, rounded, recipe, "diffusion", forcefield_bytes=initial)
    assert any(item["section"] == "Pair Coeffs" and item["type"] == 2
               and item["accepted_by"] == "lammps_write_data_6g" for item in audit["coefficient_rounding"])
    for changed in (rounded.replace(b"2.93729", b"2.93730"), rounded.replace(b"15.9994", b"15.999"),
                    rounded.replace(b"4 2 2 0", b"4 2 2 0.000001")):
        with pytest.raises(ValueError):
            _validate_state(initial, changed, recipe, "diffusion", forcefield_bytes=initial)


def test_downstream_restoration_independently_binds_executable_commands_to_original_model():
    from suan.lammps.pet_protocol import default_recipe, make_stage_files
    from suan.workflows.pet_study import _validate_exact_forcefield
    original = toy_state().replace(b"1 0.1 3.4", b"1 0.1 3.412345678901234")
    original = original.replace(b"0 improper types", b"1 improper types").replace(
        b"Atoms # full", b"Improper Coeffs # cvff\n\n1 10 -1 2\n\nAtoms # full")
    scripts = make_stage_files(default_recipe(), "tg", "pair_style lj/cut 12\nread_data pet.data\n",
                               temperature=600., original_data_text=original.decode())
    audit = _validate_exact_forcefield(original, scripts)
    assert audit["original_forcefield_data_sha256"] == hashlib.sha256(original).hexdigest()
    sigma_text = format(3.412345678901234, ".17g")
    for edit in (
        lambda files: files.update({"forcefield-exact.in": files["forcefield-exact.in"].replace(sigma_text, "3.41235")}),
        lambda files: files.update({"forcefield-exact.in": files["forcefield-exact.in"] + "pair_coeff 1 1 0.1 3.412345678901234\n"}),
        lambda files: files.update({"forcefield-exact.in": files["forcefield-exact.in"] + "run 100\n"}),
        lambda files: files.update({"forcefield-exact.in": files["forcefield-exact.in"].replace("improper_coeff 1 10 -1 2", "improper_coeff 1 10 -1.0 2.0")}),
        lambda files: files.update({"model.in": files["model.in"].replace("include forcefield-exact.in\n", "")}),
        lambda files: files.update({"forcefield-exact.json": files["forcefield-exact.json"].replace(audit["original_forcefield_data_sha256"], "0" * 64)}),
    ):
        changed = deepcopy(scripts)
        edit(changed)
        assert changed != scripts
        # Updating the companion hash cannot authorize altered executable values.
        metadata = json.loads(changed["forcefield-exact.json"])
        metadata["commands_sha256"] = hashlib.sha256(changed["forcefield-exact.in"].encode()).hexdigest()
        changed["forcefield-exact.json"] = json.dumps(metadata)
        with pytest.raises(ValueError, match="exact coefficient restoration"):
            _validate_exact_forcefield(original, changed)


def test_cvff_discrete_sign_and_multiplicity_cannot_use_float_tolerances():
    from suan.lammps.pet_protocol import default_recipe
    from suan.workflows.pet_study import _validate_state
    original = toy_state().replace(b"0 improper types", b"1 improper types").replace(
        b"Atoms # full", b"Improper Coeffs # cvff\n\n1 10 -1 2\n\nAtoms # full")
    assert _validate_state(original, original, default_recipe(), "tg")["coefficient_rounding"] == []
    for changed in (original.replace(b"1 10 -1 2", b"1 10 -0.9999999999999 2"),
                    original.replace(b"1 10 -1 2", b"1 10 -1 2.0000000000001")):
        with pytest.raises(ValueError, match="force-field coefficients"):
            _validate_state(original, changed, default_recipe(), "tg", forcefield_bytes=original)


def test_tg_refuses_rounded_restoration_before_creating_a_case_or_submitting(study, monkeypatch):
    import threading
    from suan.lammps import pet_protocol
    from suan.workflows import pet_study
    s = study
    made = create(s)
    original = toy_state().replace(b"1 0.1 3.4", b"1 0.1 3.412345678901234")
    source = {"snapshot_id": "test-frozen-state", "files": {}}
    monkeypatch.setattr(pet_study, "_frozen_files", lambda *args: {"case/state.data": toy_state()})
    generator = pet_protocol.make_stage_files

    def wrong_restore(*args, **kwargs):
        files = generator(*args, **kwargs)
        # A self-consistent companion hash still cannot authorize rounded
        # coefficients where executable original precision is required.
        files["forcefield-exact.in"] = files["forcefield-exact.in"].replace(format(3.412345678901234, ".17g"), "3.41235")
        metadata = json.loads(files["forcefield-exact.json"])
        metadata["commands_sha256"] = hashlib.sha256(files["forcefield-exact.in"].encode()).hexdigest()
        files["forcefield-exact.json"] = json.dumps(metadata)
        return files

    monkeypatch.setattr(pet_protocol, "make_stage_files", wrong_restore)
    monkeypatch.setattr(s["service"], "_case", lambda *args: pytest.fail("Invalid restoration reached case creation"))
    initial_revision = revision(s)
    with pytest.raises(ValueError, match="exact coefficient restoration"):
        s["service"]._stage(s["p"], made["study_id"], "property:tg:0", "tg", made["recipe"],
            {"pet.data": original, "model.in": b"pair_style lj/cut 12\nread_data pet.data\n"}, source,
            made["simulation"], {}, threading.Event(), time.monotonic() + 5, temperature=600.)
    assert revision(s) == initial_revision and not s["runtime"][0].tasks()


def test_wait_budget_expiry_keeps_an_accepted_task_for_explicit_resume(study):
    s = study
    (s["tmp"] / "lmp.json").write_text(json.dumps({"mode": "slow"}))
    made = create(s, wait_seconds=1)
    assert made["wait_seconds"] == 1
    s["service"].start(made["study_id"], expected_revision=revision(s))
    run = done(s, made["run_id"], timeout=30)
    assert not run["complete"] and "time budget" in run["tasks"][0]["error"]["message"]
    client, supervisor, _, _ = s["runtime"]
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        supervisor.tick()
        result = s["service"].get(made["study_id"])
        progress = (result["stages"].get("relax", {}).get("tasks") or [{}])[0].get("progress") or {}
        if progress.get("task_id") and client.task(progress["task_id"])["state"] == "running":
            break
        time.sleep(.02)
    else:
        pytest.fail("Accepted solver task was lost on coordinator timeout")
    assert len(client.tasks()) == 1 and len(s["calls"]) == 1
    s["service"].cancel(made["study_id"], expected_revision=revision(s))


@pytest.mark.parametrize("completed,restore", [(False, True), (True, True), (False, False)])
def test_off_protocol_frozen_child_is_not_adopted_after_its_case_was_approved(study, completed, restore):
    import threading
    from suan.workflows import lammps
    from suan.workflows.pet_study import _workflow_document, _sha
    s = study
    made = create(s)
    study_id, key = made["study_id"], "relax"
    files = {"input-state.data": toy_state(), "model.in": b"pair_style lj/cut 12\nread_data input-state.data\n",
             "in.relax": b"units real\natom_style full\nvariable temperature index 600\nvariable steps index 100\ninclude model.in\nvelocity all create ${temperature} 42\nthermo 10\nrun ${steps}\n"}
    parameters = {"temperature": 600., "steps": 100}
    record, approved_values = s["service"]._case(s["p"], study_id, key, files, parameters)
    workflow, identity = _id(study_id, key + ":workflow"), _id(study_id, key + ":run")
    document = _workflow_document(lammps.TABLE_ID, "lammps/1", parameters={}, metadata={
        "format": "stk.pet-study/1", "study_id": study_id, "stage": key, "recipe_sha256": _sha(made["recipe"])})
    s["p"].workflows.create("Off-protocol fixture", document, workflow_id=workflow, expected_revision=revision(s))
    s["p"].apply([{"op": "set_cell", "table_id": lammps.TABLE_ID, "record_id": record,
                   "field_id": lammps.FIELD_IDS["temperature"], "value": 900.}], expected_revision=revision(s))
    s["p"].workflow_runs.prepare(workflow, [record], run_id=identity, expected_revision=revision(s),
                                  connection=s["connection"], options=s["options"])
    if completed:
        directory = next(value["directory"] for value in s["api"].projects.list() if value["handle"] == s["p"].handle)
        store = ProjectStore(directory)
        owner = str(uuid4())
        store.workflow_runs.start(identity, executor_id=owner)
        attempt = store.workflow_runs.begin_attempt(identity, "execute", record, executor_id=owner)
        store.workflow_runs.finish_attempt(identity, "execute", record, attempt, "succeeded", executor_id=owner, produced={})
        store.workflow_runs.stop(identity, executor_id=owner)
    if restore:
        s["p"].apply([{"op": "set_cell", "table_id": lammps.TABLE_ID, "record_id": record,
                       "field_id": lammps.FIELD_IDS["temperature"], "value": 600.}], expected_revision=revision(s))
    with pytest.raises(ValueError, match="frozen parameters or source"):
        s["service"]._child(s["p"], study_id, key, lammps.TABLE_ID, record, "lammps/1", {}, made["recipe"],
                              made["simulation"], {}, threading.Event(), time.monotonic()+5,
                              approved_values=approved_values)
    assert not s["runtime"][0].tasks()


def test_prepared_multirow_child_is_rejected_before_linking_or_starting_any_row(study):
    import threading
    from suan.workflows import lammps
    from suan.workflows.pet_study import _workflow_document, _sha
    s = study
    made = create(s)
    study_id, key = made["study_id"], "relax"
    files = {"input-state.data": toy_state(), "model.in": b"pair_style lj/cut 12\nread_data input-state.data\n",
             "in.relax": b"units real\natom_style full\nvariable temperature index 600\nvariable steps index 100\ninclude model.in\nvelocity all create ${temperature} 42\nthermo 10\nrun ${steps}\n"}
    parameters = {"temperature": 600., "steps": 100}
    record, approved = s["service"]._case(s["p"], study_id, key, files, parameters)
    extra_record, _ = s["service"]._case(s["p"], study_id, "extra-case-fixture", files, parameters)
    workflow, identity = _id(study_id, key + ":workflow"), _id(study_id, key + ":run")
    document = _workflow_document(lammps.TABLE_ID, "lammps/1", parameters={}, metadata={
        "format": "stk.pet-study/1", "study_id": study_id, "stage": key, "recipe_sha256": _sha(made["recipe"])})
    s["p"].workflows.create("Prepared multirow fixture", document, workflow_id=workflow, expected_revision=revision(s))
    prepared = s["p"].workflow_runs.prepare(workflow, [record, extra_record], run_id=identity,
        expected_revision=revision(s), connection=s["connection"], options=s["options"])
    assert len(prepared["rows"]) == 2
    before = revision(s)
    with pytest.raises(ValueError, match="child inputs"):
        s["service"]._child(s["p"], study_id, key, lammps.TABLE_ID, record, "lammps/1", {}, made["recipe"],
            made["simulation"], {}, threading.Event(), time.monotonic() + 5, approved_values=approved)
    unchanged = s["p"].workflow_runs.get(identity)
    assert unchanged["status"] == "prepared" and unchanged["tasks"] == prepared["tasks"]
    assert revision(s) == before and s["service"].get(study_id)["objects"] == {}
    assert not s["runtime"][0].tasks() and not s["runtime"][0].workspaces()


@pytest.mark.parametrize("field,value", [("script", "model.in"), ("attempt", 2), ("pressure", 2.)])
def test_owned_stage_case_cannot_change_script_attempt_or_unused_parameters(study, field, value):
    from suan.workflows import lammps
    s = study
    made = create(s)
    files = {"input-state.data": toy_state(), "model.in": b"pair_style lj/cut 12\nread_data input-state.data\n",
             "in.relax": b"units real\natom_style full\nvariable temperature index 600\nvariable steps index 100\ninclude model.in\nvelocity all create ${temperature} 42\nrun ${steps}\n"}
    parameters = {"temperature": 600., "steps": 100}
    record, _ = s["service"]._case(s["p"], made["study_id"], "relax", files, parameters)
    s["p"].apply([{"op": "set_cell", "table_id": lammps.TABLE_ID, "record_id": record,
                   "field_id": lammps.FIELD_IDS[field], "value": value}], expected_revision=revision(s))
    with pytest.raises(ValueError, match="derived case changed"):
        s["service"]._case(s["p"], made["study_id"], "relax", files, parameters)
    assert not s["runtime"][0].tasks()


def test_owned_stage_case_cannot_forge_the_script_parameter_list(study):
    from suan.workflows import lammps
    s = study
    made = create(s)
    files = {"input-state.data": toy_state(), "model.in": b"pair_style lj/cut 12\nread_data input-state.data\n",
             "in.relax": b"units real\nvariable temperature index 600\ninclude model.in\nvelocity all create ${temperature} 42\nrun 100\n"}
    parameters = {"temperature": 600.}
    record, approved = s["service"]._case(s["p"], made["study_id"], "relax", files, parameters)
    source = approved["source"]
    source["parameters"] = []
    s["p"].apply([{"op": "set_cell", "table_id": lammps.TABLE_ID, "record_id": record,
                   "field_id": lammps.FIELD_IDS["source"], "value": source}], expected_revision=revision(s))
    with pytest.raises(ValueError, match="derived case changed"):
        s["service"]._case(s["p"], made["study_id"], "relax", files, parameters)
    assert not s["runtime"][0].tasks()


def test_status_rejects_an_analysis_without_this_studys_completed_source_stage(study):
    from suan.graph.catalog import load_preset
    s = study
    made = create(s)
    data = s["tmp"] / "foreign.csv"
    data.write_text("Strain Stress\n0 0\n.01 .1\n.02 .2\n")
    indexed = s["p"].files.index([data], expected_revision=revision(s))
    captured = s["p"].snapshots.capture(indexed["record_ids"], expected_revision=indexed["revision"])
    definition = _id(made["study_id"], "analysis:modulus:definition")
    s["p"].analyses.create("Foreign observations", {"format": "stk.analysis-document/1", "graph": load_preset("lammps-modulus"),
        "parameters": {"path": "case/stress-strain.dat"}, "outputs": ["summary"]},
        analysis_id=definition, expected_revision=revision(s))
    run_id = str(uuid4())
    snapshot_id = captured["snapshot"]["id"]
    s["p"].analysis_runs.prepare(definition, snapshot_id, {"data": {"case/stress-strain.dat": indexed["record_ids"][0]}},
                                  run_id=run_id, expected_revision=revision(s))
    s["service"]._save(s["p"], made["study_id"], made["run_id"], {"analysis:modulus": {
        "analysis_id": definition, "run_id": run_id, "snapshot_id": snapshot_id, "previous_run_ids": []}})
    with pytest.raises(ValueError, match="analysis belongs to a different study"):
        s["service"].get(made["study_id"])
    assert s["calls"] == []


@pytest.mark.parametrize("wrong", ["bindings", "definition", "parameter_overrides"])
def test_prepared_analysis_cannot_replace_frozen_sources_definition_or_fit_window(study, wrong):
    from suan.graph.catalog import load_preset
    s = study
    made = create(s)
    data, note = s["tmp"] / "msd.dat", s["tmp"] / "note.txt"
    data.write_text("Step Time MSD\n0 0 0\n1 2500 1\n2 5000 2\n3 7500 3\n4 10000 4\n")
    note.write_text("Synthetic source-binding negative-test fixture\n")
    indexed = s["p"].files.index([data, note], expected_revision=revision(s))
    captured = s["p"].snapshots.capture(indexed["record_ids"], expected_revision=indexed["revision"])
    source = {"snapshot_id": captured["snapshot"]["id"],
              "files": dict(zip(("case/msd.dat", "case/note.txt"), indexed["record_ids"]))}
    graph = load_preset("lammps-diffusion")
    graph["outputs"]["observations"] = "data.out"
    values = made["recipe"]["diffusion"]
    document = {"format": "stk.analysis-document/1", "graph": graph,
                "parameters": {"path": "case/msd.dat", "time_min": values["time_min"],
                               "time_max": values["time_max"], "dimensions": values["dimensions"]},
                "outputs": ["observations", "summary", "fit", "diagnostics", "plot"]}
    definition = _id(made["study_id"], "analysis:diffusion:definition")
    s["p"].analyses.create("Expected study analysis", document, analysis_id=definition, expected_revision=revision(s))
    selected_definition = definition
    if wrong == "definition":
        selected_definition = str(uuid4())
        s["p"].analyses.create("Other definition", document, analysis_id=selected_definition, expected_revision=revision(s))
    bindings = {"data": dict(source["files"])}
    if wrong == "bindings":
        bindings["data"]["case/msd.dat"] = indexed["record_ids"][1]
    run_id = _id(made["study_id"], "analysis:diffusion:attempt:1")
    prepared = s["p"].analysis_runs.prepare(selected_definition, source["snapshot_id"], bindings,
        run_id=run_id, expected_revision=revision(s),
        parameter_overrides={"time_min": 3000.} if wrong == "parameter_overrides" else None)
    before = revision(s)
    objects = {}
    with pytest.raises(ValueError, match="full source bindings"):
        s["service"]._analysis(s["p"], made["study_id"], "diffusion", made["recipe"], source, objects, 1)
    unchanged = s["p"].analysis_runs.get(run_id)
    assert unchanged == prepared and unchanged["status"] == "prepared"
    assert revision(s) == before and objects == {} and s["service"].get(made["study_id"])["objects"] == {}
    assert s["calls"] == [] and not s["runtime"][0].tasks()
    # A forged ordinary association must not make status display the same
    # off-protocol analysis as an authorized study result either. Build only
    # canonical journals here; no solver or analysis executor is started.
    from suan.workflows import lammps
    from suan.workflows.pet_study import _workflow_document, _sha
    key = "property:diffusion"
    case_files = {"input-state.data": toy_state(), "model.in": b"pair_style lj/cut 12\nread_data input-state.data\n",
                  "in.diffusion": b"units real\natom_style full\nvariable temperature index 600\nvariable steps index 100\ninclude model.in\nvelocity all create ${temperature} 42\nthermo 10\nrun ${steps}\n"}
    record, _ = s["service"]._case(s["p"], made["study_id"], key, case_files, {"temperature": 600., "steps": 100})
    workflow, child_id = _id(made["study_id"], key + ":workflow"), _id(made["study_id"], key + ":run")
    child_doc = _workflow_document(lammps.TABLE_ID, "lammps/1", parameters={}, metadata={
        "format": "stk.pet-study/1", "study_id": made["study_id"], "stage": key, "recipe_sha256": _sha(made["recipe"])})
    s["p"].workflows.create("Synthetic completed source journal", child_doc, workflow_id=workflow, expected_revision=revision(s))
    s["p"].workflow_runs.prepare(workflow, [record], run_id=child_id, expected_revision=revision(s),
                                 connection=s["connection"], options=s["options"])
    directory = next(item["directory"] for item in s["api"].projects.list() if item["handle"] == s["p"].handle)
    store, owner = ProjectStore(directory), str(uuid4())
    store.workflow_runs.start(child_id, executor_id=owner)
    attempt = store.workflow_runs.begin_attempt(child_id, "execute", record, executor_id=owner)
    store.workflow_runs.finish_attempt(child_id, "execute", record, attempt, "succeeded", executor_id=owner, produced=source)
    store.workflow_runs.stop(child_id, executor_id=owner)
    s["service"]._save(s["p"], made["study_id"], made["run_id"], {
        key: {"workflow_id": workflow, "run_id": child_id, "record_id": record},
        "analysis:diffusion": {"analysis_id": definition, "run_id": run_id,
                               "snapshot_id": source["snapshot_id"], "previous_run_ids": []}})
    with pytest.raises(ValueError, match="full source bindings"):
        s["service"].get(made["study_id"])
    assert s["p"].analysis_runs.get(run_id)["status"] == "prepared" and not s["runtime"][0].tasks()
