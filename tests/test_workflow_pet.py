"""Local PET workflow and isolated worker transport; molecular physics has separate tests."""
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from uuid import uuid4

import psutil
import pytest

from suan.project import ProjectError, ProjectStore
from suan.scripting import API
from suan.workflows import pet, templates
from test_bridge_workflow_runs import settled
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


@pytest.fixture
def worker(tmp_path, monkeypatch):
    """Use real subprocesses without mBuild: public parameter and artifact transport only."""
    from suan.lammps.pet import forcefield_text, profile
    control = tmp_path / "control.json"
    control.write_text(json.dumps({"mode": "ok", "pids": str(tmp_path / "pids.json")}))
    script = tmp_path / "fake-worker.py"
    script.write_text(
        "import argparse,hashlib,json,os,pathlib,subprocess,sys,time\n"
        "profile=" + repr(profile()) + "\n"
        "xml=" + repr(forcefield_text()) + "\n"
        "p=argparse.ArgumentParser(); p.add_argument('--parameters'); p.add_argument('--out'); p.add_argument('--packmol')\n"
        "a=p.parse_args(); cfg=json.loads(pathlib.Path(" + repr(str(control)) + ").read_text())\n"
        "params=json.loads(pathlib.Path(a.parameters).read_text()); mode=cfg['mode']\n"
        "if mode=='slow':\n"
        " child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
        " pids=pathlib.Path(cfg['pids']); temporary=pids.with_suffix('.tmp')\n"
        " temporary.write_text(json.dumps([os.getpid(),child.pid])); temporary.replace(pids)\n"
        " time.sleep(60)\n"
        "if mode=='error':\n"
        " print('BEGIN '+('x'*40000)+' useful failure',flush=True); sys.exit(7)\n"
        "out=pathlib.Path(a.out); out.mkdir()\n"
        "for name in " + repr(pet.OUTPUTS) + ":\n"
        " if name!='pet-model.json': (out/name).write_text(json.dumps({'parameters':params,'name':name})+'\\n')\n"
        "(out/'forcefield.xml').write_bytes(xml.encode('utf-8'))\n"
        "canonical=json.dumps(profile,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')\n"
        "n=params['chain_length']; count=params['chain_count']\n"
        "report={'format':'stk.pet-model/1','profile_id':'stk.pet.opls-mk2022/1','parameters':dict(params),\n"
        " 'forcefield':profile,'profile_canonical_sha256':hashlib.sha256(canonical).hexdigest(),\n"
        " 'forcefield_xml_sha256':hashlib.sha256(xml.encode('utf-8')).hexdigest(),\n"
        " 'validation':{'atoms':(22*n+3)*count,'chain_count':count,'formula_per_chain':{'C':10*n,'H':8*n+2,'O':4*n+1},\n"
        "               'chain_charge_e':[0.0]*count},'environment':sorted(os.environ),\n"
        " 'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}}\n"
        "if mode=='bad_version': report['format']='stk.pet-model/2'\n"
        "if mode=='bad_id': report['profile_id']='unsupported-profile/1'\n"
        "if mode=='bad_parameters': report['parameters']['seed']+=1\n"
        "if mode=='bad_profile': report['forcefield']['atom_types'][0]['charge_e']=0.0\n"
        "if mode=='bad_profile_hash': report['profile_canonical_sha256']='0'*64\n"
        "if mode=='bad_file_hash': report['files']['pet.data']='0'*64\n"
        "if mode=='bad_xml_hash': report['forcefield_xml_sha256']='0'*64\n"
        "if mode=='tampered_xml':\n"
        " (out/'forcefield.xml').write_bytes(b'altered XML'); digest=hashlib.sha256(b'altered XML').hexdigest()\n"
        " report['files']['forcefield.xml']=digest; report['forcefield_xml_sha256']=digest\n"
        "if mode=='bad_atom_count': report['validation']['atoms']-=1\n"
        "if mode=='bad_chain_count': report['validation']['chain_count']+=1\n"
        "if mode=='bad_formula': report['validation']['formula_per_chain']['O']-=1\n"
        "if mode=='bad_charge': report['validation']['chain_charge_e'][0]=0.001\n"
        "if mode=='charge_boolean': report['validation']['chain_charge_e'][0]=False\n"
        "if mode=='missing_charge': report['validation']['chain_charge_e'].pop()\n"
        "if mode=='nan': report['extra']=float('nan')\n"
        "if mode=='huge_float': report['extra']='replace-large-number'\n"
        "text=json.dumps(report)+'\\n'\n"
        "if mode=='duplicate': text=text.replace('{','{\\\"format\\\":\\\"stk.pet-model/1\\\",',1)\n"
        "if mode=='huge_float': text=text.replace('\\\"replace-large-number\\\"','1e999')\n"
        "if mode=='oversized_manifest': text+=' '*(2*1024*1024)\n"
        "(out/'pet-model.json').write_text(text)\n"
        "if mode=='extra': (out/'unexpected.txt').write_text('extra')\n"
        "if mode=='missing': (out/'pet.data').unlink()\n"
        "if mode=='link':\n"
        " (out/'pet.data').unlink(); (out/'pet.data').symlink_to(pathlib.Path(a.parameters))\n"
        "if mode=='race':\n"
        " destination=pathlib.Path(cfg['destination']); destination.mkdir(); (destination/'owned.txt').write_text('keep')\n",
        encoding="utf-8")
    bootstrap = "import runpy,sys;sys.argv.pop(1);runpy.run_path(" + repr(str(script)) + ",run_name='__main__')"
    monkeypatch.setattr(pet, "_BOOTSTRAP", bootstrap)
    monkeypatch.setattr("suan.modules.find_program", lambda module, name=None: sys.executable)
    return {"control": control, "pids": tmp_path / "pids.json", "destination": tmp_path / "case"}


def mode(worker, value):
    worker["control"].write_text(json.dumps({"mode": value, "pids": str(worker["pids"]),
                                           "destination": str(worker["destination"])}))


def assert_clean(worker):
    assert not worker["destination"].exists()
    assert not list(worker["destination"].parent.glob(".stk-pet-*"))


def test_worker_receives_only_validated_parameters_and_operating_system_environment(worker, monkeypatch):
    monkeypatch.setenv("STK_TEST_SECRET_TOKEN", "abcdefghijklmnopqrstu")
    monkeypatch.setenv("https_proxy", "http://unused.invalid")
    monkeypatch.setenv("PYTHONPATH", "untrusted-unused-path")
    calls = []
    original = subprocess.Popen

    def record(argv, **options):
        calls.append((argv, options))
        return original(argv, **options)

    monkeypatch.setattr(pet.subprocess, "Popen", record)
    output = pet.model_pet(dict(pet.DEFAULT_PARAMETERS), worker["destination"])
    assert output == worker["destination"]
    assert {path.name for path in output.iterdir()} == set(pet.OUTPUTS)
    summary = json.loads((output / "pet-model.json").read_text())
    assert summary["parameters"] == pet.DEFAULT_PARAMETERS
    assert not ({"STK_TEST_SECRET_TOKEN", "STK_TOKEN_PLAN_API_KEY", "STK_TOKEN_PLAN_MODEL",
                 "https_proxy", "PYTHONPATH"} & set(summary["environment"]))
    argv, options = calls[0]
    assert argv[1:3] == ["-I", "-c"] and options.get("shell", False) is False
    assert options["start_new_session"] == (os.name != "nt")
    assert not list(output.parent.glob(".stk-pet-*"))


@pytest.mark.parametrize("module", ["molecular-modeling", "packmol"])
def test_missing_modules_are_reported_without_installing_or_creating_outputs(worker, monkeypatch, module):
    monkeypatch.setattr("suan.modules.find_program", lambda identity, name=None: None if identity == module else sys.executable)
    with pytest.raises(ProjectError, match=module + " module"):
        pet.model_pet(dict(pet.DEFAULT_PARAMETERS), worker["destination"])
    assert_clean(worker)


def test_existing_outputs_are_preserved(worker):
    destination = worker["destination"]
    destination.mkdir()
    (destination / "owned.txt").write_text("keep")
    with pytest.raises(ProjectError, match="new output directory"):
        pet.model_pet(dict(pet.DEFAULT_PARAMETERS), destination)
    assert (destination / "owned.txt").read_text() == "keep"


@pytest.mark.skipif(os.name == "nt", reason="symbolic links require Windows privileges")
def test_destination_links_and_worker_output_links_are_refused(worker, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    worker["destination"].symlink_to(target, target_is_directory=True)
    with pytest.raises(ProjectError, match="new output directory"):
        pet.model_pet(dict(pet.DEFAULT_PARAMETERS), worker["destination"])
    worker["destination"].unlink()
    mode(worker, "link")
    with pytest.raises(ProjectError, match="regular files"):
        pet.model_pet(dict(pet.DEFAULT_PARAMETERS), worker["destination"])
    assert_clean(worker)
    assert not list(target.iterdir())


@pytest.mark.parametrize("variant", ["extra", "missing"])
def test_incomplete_or_unexpected_artifacts_are_never_published(worker, variant):
    mode(worker, variant)
    with pytest.raises(ProjectError, match="exactly the declared case files"):
        pet.model_pet(dict(pet.DEFAULT_PARAMETERS), worker["destination"])
    assert_clean(worker)


def test_failure_reports_a_bounded_error_tail_and_removes_staging(worker):
    mode(worker, "error")
    with pytest.raises(ProjectError) as raised:
        pet.model_pet(dict(pet.DEFAULT_PARAMETERS), worker["destination"])
    message = str(raised.value)
    assert message.startswith("PET modeling exited with 7:") and message.endswith("useful failure")
    assert "BEGIN" not in message and len(message) < pet.ERROR_TAIL_BYTES + 100
    assert_clean(worker)


@pytest.mark.parametrize("variant,message", [
    ("bad_version", "unsupported model/profile"), ("bad_id", "unsupported model/profile"),
    ("bad_parameters", "frozen modeling parameters"),
    ("bad_profile", "complete shipped force-field profile"),
    ("bad_profile_hash", "complete shipped force-field profile"),
    ("bad_file_hash", "seven actual artifact hashes"),
    ("bad_xml_hash", "shipped resource and recorded hash"),
    ("tampered_xml", "shipped resource and recorded hash"),
    ("bad_atom_count", "chain count or COOH/OH formula"),
    ("bad_chain_count", "chain count or COOH/OH formula"),
    ("bad_formula", "chain count or COOH/OH formula"),
    ("bad_charge", "finite neutral charges"),
    ("charge_boolean", "finite neutral charges"),
    ("missing_charge", "every chain charge"),
    ("nan", "finite UTF-8 JSON with unique keys"),
    ("huge_float", "finite UTF-8 JSON with unique keys"),
    ("duplicate", "finite UTF-8 JSON with unique keys"),
    ("oversized_manifest", "2 MiB limit"),
])
def test_inconsistent_model_manifest_is_never_published(worker, variant, message):
    mode(worker, variant)
    with pytest.raises(ProjectError, match=message):
        pet.model_pet(dict(pet.DEFAULT_PARAMETERS), worker["destination"])
    assert_clean(worker)


def test_cancel_kills_the_modeling_process_and_its_packmol_descendant(worker):
    mode(worker, "slow")
    cancel, outcomes = threading.Event(), queue.Queue()

    def run():
        try:
            pet.model_pet(dict(pet.DEFAULT_PARAMETERS), worker["destination"], cancel=cancel)
        except Exception as error:
            outcomes.put(error)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not worker["pids"].is_file():
            assert time.monotonic() < deadline
            time.sleep(0.01)
        pids = json.loads(worker["pids"].read_text())
    finally:
        cancel.set()
        thread.join(10)
    assert not thread.is_alive()
    assert isinstance(outcomes.get_nowait(), pet.ModelingCancelled)
    for pid in pids:
        try:
            process = psutil.Process(pid)
        except psutil.NoSuchProcess:
            continue
        assert process.status() == psutil.STATUS_ZOMBIE or not process.is_running()
    assert_clean(worker)


def test_timeout_cleans_all_outputs(worker):
    mode(worker, "slow")
    with pytest.raises(ProjectError, match="time budget"):
        pet.model_pet(dict(pet.DEFAULT_PARAMETERS), worker["destination"], timeout=0.3)
    assert_clean(worker)


def test_a_destination_created_during_modeling_is_not_replaced(worker):
    mode(worker, "race")
    with pytest.raises(FileExistsError):
        pet.model_pet(dict(pet.DEFAULT_PARAMETERS), worker["destination"])
    assert (worker["destination"] / "owned.txt").read_text() == "keep"
    assert not list(worker["destination"].parent.glob(".stk-pet-*"))


def test_exclusive_publication_also_preserves_an_empty_existing_directory(tmp_path):
    source, destination = tmp_path / "stage", tmp_path / "owned"
    source.mkdir()
    (source / "new.txt").write_text("new")
    destination.mkdir()
    with pytest.raises(FileExistsError):
        pet._publish(source, destination)
    assert not list(destination.iterdir()) and (source / "new.txt").is_file()


@pytest.fixture
def project(inproc, tmp_path):
    harness = inproc()
    store = ProjectStore.create(tmp_path / "project", "PET modeling")
    handle = harness.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    api = API(lambda operation, parameters: harness.call(operation, parameters))
    api._project_handle = handle
    return harness, store, handle, api


def test_creation_saves_a_local_workflow_without_running_or_migrating_the_project(project, monkeypatch):
    harness, store, _, api = project
    monkeypatch.setattr(pet, "model_pet", lambda *args, **kwargs: pytest.fail("creation must execute nothing"))
    made = api.lammps.create_pet_workflow(expected_revision=0)
    table = next(table for table in store.snapshot()["tables"] if table["id"] == made["table_id"])
    assert {field["id"]: field["type"] for field in table["fields"]} == {
        made["field_ids"][key]: specification[1] for key, specification in pet.FIELDS.items()}
    values = table["records"][0]["values"]
    assert {key: values[field] for key, field in made["field_ids"].items()} == pet.DEFAULT_PARAMETERS
    document = store.workflows.get(made["workflow_id"])["workflow"]["document"]
    assert store.workflows.validate(document)["ok"]
    assert [step["id"] for step in document["steps"]] == ["cases", "model"]
    assert templates.workflow_templates()["pet-model/1"].local
    assert "pet-model/1" not in templates.remote_templates()
    assert store.workflow_runs.list()["runs"] == [] and made["revision"] == 2
    assert not harness.violations


@pytest.mark.parametrize("rows", [[], [{}] * 101, [None], [{"chain_length": 1}], [{"seed": True}], [{"packing_density": float("inf")}],
                                  [{"unknown": 1}]])
def test_invalid_rows_leave_the_project_unchanged(project, rows):
    _, store, _, api = project
    before = store.snapshot()
    with pytest.raises(ValueError):
        pet.create_pet_workflow(api, expected_revision=0, rows=rows)
    assert store.snapshot() == before and store.workflows.list()["total"] == 0


def write_outputs(parameters, directory):
    directory = Path(directory)
    directory.mkdir()
    for name in pet.OUTPUTS:
        (directory / name).write_text(json.dumps(parameters, sort_keys=True) + "\n")


def test_each_row_uses_frozen_parameters_and_freezes_every_model_artifact(project, monkeypatch):
    harness, store, handle, api = project
    calls = []

    def build(parameters, directory, *, cancel=None):
        assert cancel is not None
        calls.append(dict(parameters))
        write_outputs(parameters, directory)

    monkeypatch.setattr(pet, "model_pet", build)
    made = pet.create_pet_workflow(api, expected_revision=0, rows=[{}, {"chain_length": 8, "seed": 42}])
    run = api.project.workflow_runs.prepare(made["workflow_id"], made["record_ids"], run_id=str(uuid4()),
                                            expected_revision=made["revision"])
    frozen = run["parameters"]["model"]
    store.apply([{"op": "set_cell", "table_id": made["table_id"], "record_id": made["record_ids"][0],
                  "field_id": made["field_ids"]["seed"], "value": 99}], expected_revision=made["revision"])
    api.project.workflow_runs.start(run["id"])
    done = settled(harness, handle, run["id"])
    assert done["complete"] and done["counts"] == {"succeeded": 2}
    assert calls == [frozen[row] for row in made["record_ids"]]
    assert calls[0]["seed"] == pet.DEFAULT_PARAMETERS["seed"]
    for task in done["tasks"]:
        produced = task["produced"]
        assert set(produced["files"]) == set(pet.OUTPUTS)
        manifest = store.snapshots.get(produced["snapshot_id"])["manifest"]["files"]
        expected = {record: hashlib.sha256((store.directory / produced["directory"] / name).read_bytes()).hexdigest()
                    for name, record in produced["files"].items()}
        assert {item["record_id"]: item["sha256"] for item in manifest} == expected
    assert store.workflow_runs.get(run["id"])["plan_sha256"] == run["plan_sha256"]


def test_reopening_preserves_model_plan_and_immutable_generated_input_snapshot(project, monkeypatch):
    harness, store, handle, api = project
    calls = []

    def build(parameters, directory, *, cancel=None):
        calls.append(dict(parameters))
        write_outputs(parameters, directory)

    monkeypatch.setattr(pet, "model_pet", build)
    made = api.lammps.create_pet_workflow(expected_revision=0)
    run = api.project.workflow_runs.prepare(made["workflow_id"], made["record_ids"], run_id=str(uuid4()),
                                            expected_revision=made["revision"])
    api.project.workflow_runs.start(run["id"])
    done = settled(harness, handle, run["id"])
    produced = done["tasks"][0]["produced"]
    record_id = produced["files"]["pet.data"]
    frozen = store.snapshots.resolve(produced["snapshot_id"], record_id)
    original = Path(frozen["path"]).read_bytes()
    # Editing the ordinary generated file cannot rewrite its already frozen object.
    (store.directory / produced["directory"] / "pet.data").write_text("changed after generation")
    api.project.close()
    opened = api.projects.open(store.directory)
    api._project_handle = opened.handle
    reopened = api.project.workflow_runs.get(run["id"])
    assert reopened["complete"] and reopened["plan_sha256"] == run["plan_sha256"]
    assert reopened["tasks"][0]["produced"] == produced and calls == [pet.DEFAULT_PARAMETERS]
    assert Path(store.snapshots.resolve(produced["snapshot_id"], record_id)["path"]).read_bytes() == original


def test_cancellable_modeling_records_cancelled_attempt_without_publishing_a_snapshot(project, monkeypatch):
    harness, store, handle, api = project
    entered = threading.Event()

    def build(parameters, directory, *, cancel=None):
        entered.set()
        assert cancel.wait(10)
        raise pet.ModelingCancelled("PET modeling was cancelled")

    monkeypatch.setattr(pet, "model_pet", build)
    made = pet.create_pet_workflow(api, expected_revision=0)
    run = api.project.workflow_runs.prepare(made["workflow_id"], made["record_ids"], run_id=str(uuid4()),
                                            expected_revision=made["revision"])
    api.project.workflow_runs.start(run["id"])
    assert entered.wait(10)
    api.project.workflow_runs.cancel(run["id"])
    done = settled(harness, handle, run["id"])
    assert done["counts"] == {"cancelled": 1} and done["tasks"][0]["produced"] is None
    assert store.info()["revision"] == made["revision"]


def test_another_process_can_cancel_a_modeling_task_already_in_flight(project, monkeypatch):
    harness, store, handle, api = project
    entered = threading.Event()

    def build(parameters, directory, *, cancel=None):
        entered.set()
        assert cancel.wait(10), "persistent cancellation must reach the active local worker"
        raise pet.ModelingCancelled("PET modeling was cancelled")

    monkeypatch.setattr(pet, "model_pet", build)
    made = api.lammps.create_pet_workflow(expected_revision=0)
    run = api.project.workflow_runs.prepare(made["workflow_id"], made["record_ids"], run_id=str(uuid4()),
                                            expected_revision=made["revision"])
    api.project.workflow_runs.start(run["id"])
    assert entered.wait(10)
    other = ProjectStore(store.directory)
    other.workflow_runs.request_cancel(run["id"])
    done = settled(harness, handle, run["id"])
    assert done["counts"] == {"cancelled": 1} and done["tasks"][0]["produced"] is None
    assert store.info()["revision"] == made["revision"]


def test_failed_modeling_retries_only_the_failed_row(project, monkeypatch):
    harness, _, handle, api = project
    calls = []

    def build(parameters, directory, *, cancel=None):
        calls.append(parameters["seed"])
        if parameters["seed"] == 42 and calls.count(42) == 1:
            raise ProjectError("parameterization failed")
        write_outputs(parameters, directory)

    monkeypatch.setattr(pet, "model_pet", build)
    made = pet.create_pet_workflow(api, expected_revision=0, rows=[{}, {"seed": 42}])
    run = api.project.workflow_runs.prepare(made["workflow_id"], made["record_ids"], run_id=str(uuid4()),
                                            expected_revision=made["revision"])
    api.project.workflow_runs.start(run["id"])
    first = settled(harness, handle, run["id"])
    assert first["counts"] == {"succeeded": 1, "failed": 1}
    api.project.workflow_runs.start(run["id"])
    second = settled(harness, handle, run["id"])
    assert second["complete"] and [task["attempt"] for task in second["tasks"]] == [1, 2]
    assert calls == [pet.DEFAULT_PARAMETERS["seed"], 42, 42]
