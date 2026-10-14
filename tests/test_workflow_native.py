"""Desktop buttons use fixed engine/project identities and the real project/Runtime services.

The test solver emits synthetic thermo data; these checks validate execution and
collection boundaries, not PET properties.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from conftest import finish
from lammps_fake import make_fake_lammps, write_case
from mupro_fake import make_fake_sdk
from suan.scripting import API
from suan.workflows import lammps, muferro
from suan.workflows.native import native_action
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_desktop_bridge_runtime import add_profile


@pytest.fixture
def project_api(inproc, tmp_path):
    h = inproc()
    api = API(h.call)
    p = api.projects.create(tmp_path / "project", "Native engines")
    api._project_handle = p.handle
    return {"h": h, "api": api, "p": p, "tmp": tmp_path}


def invoke(s, action, *, engine="lammps/1", **params):
    info = s["p"].snapshot()["project"]
    return native_action(s["api"], engine, action,
                         {"project_id": info["id"], "expected_revision": info["revision"], **params})


@pytest.fixture
def native_runtime(project_api, runtime, monkeypatch):
    s = project_api
    s["client"], s["supervisor"], _, _ = runtime
    for name in ("STK_ALLOW_LOCAL_MPI", "STK_MUPRO_ALLOW_LOCAL_MPI", "SLURM_JOB_ID", "PBS_JOBID"):
        monkeypatch.delenv(name, raising=False)
    s["connection"] = add_profile(s["h"], runtime)
    s["program"] = make_fake_lammps(s["tmp"] / "bin")
    first = invoke(s, "import", source=str(write_case(s["tmp"] / "case ' 中文")))["record_id"]
    s["p"].apply([{"op": "set_cell", "table_id": lammps.TABLE_ID, "record_id": first,
                   "field_id": lammps.FIELD_IDS["pressure"], "value": 1.0}],
                 expected_revision=s["p"].snapshot()["project"]["revision"])
    second = invoke(s, "clone", record_id=first)["record_id"]
    s["rows"] = [first, second]
    s["options"] = {"program": str(s["program"]), "launcher": "none"}
    return s


@pytest.mark.parametrize("engine,action,params", [
    ("arbitrary.module:method", "import", {}), ("pet-model/1", "import", {}),
    ([], "import", {}), ("lammps/1", "__dict__", {}), ("lammps/1", [], {}),
    ("lammps/1", "import", []),
    ("lammps/1", "import", {"source": "unused", "project_id": "unused"}),
    ("lammps/1", "import", {"source": "unused", "project_id": "unused", "expected_revision": 0, "project": "override"}),
])
def test_invalid_dispatch_fails_before_accessing_stk(engine, action, params):
    with pytest.raises(ValueError):
        native_action(object(), engine, action, params)


def test_project_switch_rejected_before_import(project_api):
    s = project_api
    identity = s["p"].snapshot()["project"]["id"]
    other = s["api"].projects.create(s["tmp"] / "other", "Other")
    s["api"]._project_handle = other.handle
    with pytest.raises(ValueError, match="selected project changed"):
        native_action(s["api"], "lammps/1", "import", {"project_id": identity, "expected_revision": 0,
                                                        "source": "unused"})
    assert s["p"].snapshot()["project"]["revision"] == other.snapshot()["project"]["revision"] == 0
    assert not (s["tmp"] / "other" / "inputs").exists()


@pytest.mark.parametrize("action,params", [
    ("import", {"source": "unused"}), ("clone", {"record_id": "unused"}),
    ("prepare", {"record_id": "unused", "connection": "runtime:unused"}),
    ("collect", {"run_id": "unused"}), ("view", {"run_id": "unused"}), ("logs", {"run_id": "unused"}),
    ("batch_create", {"record_ids": ["unused"], "connection": "runtime:unused"}),
    ("batch_submit", {"batch_id": "unused"}),
])
def test_stale_click_rejected_before_engine_or_runtime_access(project_api, action, params):
    s = project_api
    info = s["p"].snapshot()["project"]
    with pytest.raises(ValueError, match="Project changed"):
        native_action(s["api"], "lammps/1", action,
                      {"project_id": info["id"], "expected_revision": info["revision"] + 1, **params})
    assert s["p"].runs.list()["runs"] == []
    assert s["p"].snapshot()["project"]["revision"] == info["revision"]


def test_import_script_is_explicit_and_dispatch_cannot_cross_case_tables(project_api):
    s = project_api
    source = write_case(s["tmp"] / "many-inputs")
    (source / "in.second").write_text((source / "in.npt").read_text())
    imported = invoke(s, "import", source=str(source), script="in.second")
    table = next(t for t in s["p"].snapshot()["tables"] if t["id"] == lammps.TABLE_ID)
    assert table["records"][0]["values"][lammps.FIELD_IDS["script"]] == "in.second"
    for action in ("clone", "prepare"):
        args = {"connection": "runtime:unused"} if action == "prepare" else {}
        with pytest.raises(ValueError, match="case table"):
            invoke(s, action, record_id=imported["record_id"], table_id=muferro.TABLE_ID, **args)
        with pytest.raises(ValueError, match="MuFerro case"):
            invoke(s, action, engine="muferro/1", record_id=imported["record_id"], **args)
    with pytest.raises(ValueError, match="does not take"):
        invoke(s, "import", engine="muferro/1", source=str(source), script="in.second")
    assert s["p"].runs.list()["runs"] == []


def prepared(s):
    return invoke(s, "prepare", record_id=s["rows"][0], connection=s["connection"], options=s["options"])


def test_prepare_is_idempotent_and_options_cannot_override_pinned_arguments(native_runtime):
    s = native_runtime
    for key in ("project", "record_id", "connection", "expected_revision", "identity"):
        with pytest.raises(ValueError, match="cannot override"):
            invoke(s, "prepare", record_id=s["rows"][0], connection=s["connection"], options={key: "override"})
        with pytest.raises(ValueError, match="cannot override"):
            invoke(s, "batch_run", record_ids=s["rows"], connection=s["connection"], options={key: "override"})
    with pytest.raises(ValueError, match="must be an object"):
        invoke(s, "prepare", record_id=s["rows"][0], connection=s["connection"], options=[])
    assert s["client"].workspaces() == [] and s["client"].tasks() == []
    run = prepared(s)
    assert prepared(s)["id"] == run["id"]
    assert len(s["client"].workspaces()) == 1 and s["client"].tasks() == []
    with pytest.raises(ValueError, match="not been accepted"):
        invoke(s, "logs", run_id=run["id"])
    with pytest.raises(ValueError, match="successfully finished"):
        invoke(s, "collect", run_id=run["id"])
    with pytest.raises(ValueError, match="Collect this"):
        invoke(s, "view", run_id=run["id"])


@pytest.mark.parametrize("action", ["collect", "view", "logs"])
def test_wrong_engine_run_rejected_before_refresh_or_remote_access(native_runtime, action, monkeypatch):
    s = native_runtime
    run = prepared(s)
    call, operations = s["api"]._call, []

    def observe(operation, params):
        operations.append(operation)
        return call(operation, params)

    monkeypatch.setattr(s["api"], "_call", observe)
    with pytest.raises(ValueError, match="MuFerro project workflow"):
        invoke(s, action, engine="muferro/1", run_id=run["id"])
    assert "project.runs.refresh" not in operations
    assert not any(operation.startswith("runtime.") for operation in operations)
    assert s["client"].tasks() == []


def test_copied_label_and_table_do_not_authorize_another_runner(native_runtime):
    s = native_runtime
    plan = prepared(s)["plan"]
    spec = deepcopy(plan["spec"])
    spec["argv"] = ["{python}", "-c", "print('synthetic unrelated task')"]
    forged = s["p"].runs.prepare([{"table_id": lammps.TABLE_ID, "record_id": s["rows"][0],
        "label": plan["label"] + ":copied", "input_snapshot_id": plan["input_snapshot_id"],
        "input_bindings": plan["input_bindings"], "spec": spec}], connection=s["connection"],
        expected_revision=s["p"].snapshot()["project"]["revision"])["run_ids"][0]
    with pytest.raises(ValueError, match="LAMMPS project workflow"):
        invoke(s, "logs", run_id=forged)
    with pytest.raises(ValueError, match="LAMMPS project workflow"):
        s["api"].lammps.view(forged)
    assert s["client"].tasks() == []


def test_collect_logs_and_offline_view_reopen_and_recheck_bytes(native_runtime, monkeypatch, capsys):
    s = native_runtime
    run = prepared(s)
    task_id = s["p"].runs.submit(run["id"])["status"]["task"]["id"]
    assert finish(s["client"], s["supervisor"], task_id)["state"] == "succeeded"
    logs = invoke(s, "logs", run_id=run["id"])
    assert set(logs["streams"]) == {"stdout", "stderr"}
    collected = invoke(s, "collect", run_id=run["id"])
    assert invoke(s, "collect", run_id=run["id"]) == collected
    assert collected["qoi"]["density"] == pytest.approx(1.4)
    s["p"].close()
    s["p"] = s["api"].projects.open(s["tmp"] / "project")
    s["api"]._project_handle = s["p"].handle
    call, operations = s["api"]._call, []

    def offline(operation, params):
        operations.append(operation)
        assert not operation.startswith("runtime.") and operation != "project.runs.refresh"
        return call(operation, params)

    monkeypatch.setattr(s["api"], "_call", offline)
    revision = s["p"].snapshot()["project"]["revision"]
    capsys.readouterr()
    viewed = invoke(s, "view", run_id=run["id"])
    shown = json.loads(capsys.readouterr().out.removeprefix("LAMMPS collected results: "))
    assert shown["file_count"] == len(viewed["files"]) and "files" not in shown
    assert viewed["table_id"] == lammps.RESULT_TABLE_ID and viewed["record_id"] == collected["record_id"]
    assert viewed["units"] == "real" and viewed["thermo"]["means"]["Density"] == pytest.approx(1.4)
    assert s["p"].snapshot()["project"]["revision"] == revision
    assert len(s["client"].tasks()) == 1
    (Path(collected["directory"]) / "log.lammps").write_text("changed synthetic log\n")
    with pytest.raises(ValueError, match="changed locally"):
        invoke(s, "view", run_id=run["id"])


def test_view_rejects_modified_summary_and_symlinked_artifacts(native_runtime):
    s = native_runtime
    run = prepared(s)
    task_id = s["p"].runs.submit(run["id"])["status"]["task"]["id"]
    assert finish(s["client"], s["supervisor"], task_id)["state"] == "succeeded"
    collected = invoke(s, "collect", run_id=run["id"])
    s["p"].apply([{"op": "set_cell", "table_id": lammps.RESULT_TABLE_ID, "record_id": collected["record_id"],
                   "field_id": lammps.RESULT_FIELD_IDS["thermo"], "value": {"means": {"Density": 9.0}}}],
                 expected_revision=s["p"].snapshot()["project"]["revision"])
    with pytest.raises(ValueError, match="thermo summary changed"):
        invoke(s, "view", run_id=run["id"])
    invoke(s, "collect", run_id=run["id"])  # explicit re-collection restores the verified table values
    original = Path(collected["directory"]) / "system.data"
    original_bytes = original.read_bytes()
    original.write_text("changed synthetic input\n")
    files = deepcopy(collected["files"])
    source_file = next(file for file in files if file["path"].endswith("/case/system.data"))
    source_file["sha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
    s["p"].apply([{"op": "set_cell", "table_id": lammps.RESULT_TABLE_ID, "record_id": collected["record_id"],
                   "field_id": lammps.RESULT_FIELD_IDS["files"], "value": files}],
                 expected_revision=s["p"].snapshot()["project"]["revision"])
    with pytest.raises(ValueError, match="frozen LAMMPS run plan"):
        invoke(s, "view", run_id=run["id"])
    original.write_bytes(original_bytes)
    invoke(s, "collect", run_id=run["id"])
    artifact = Path(collected["directory"]) / "final.data"
    outside = s["tmp"] / "outside"
    outside.write_bytes(artifact.read_bytes())
    artifact.unlink()
    artifact.symlink_to(outside)
    with pytest.raises(ValueError, match="symbolic links"):
        invoke(s, "view", run_id=run["id"])


def test_native_batches_pin_template_prepare_submit_refresh_collect(native_runtime):
    s = native_runtime
    with pytest.raises(ValueError, match="does not match"):
        invoke(s, "batch_create", record_ids=s["rows"], connection=s["connection"], template_id="muferro/1")
    batch = invoke(s, "batch_create", record_ids=s["rows"], connection=s["connection"],
                   template_id="lammps/1", options=s["options"])["id"]
    assert s["client"].workspaces() == [] and s["client"].tasks() == []
    for action in ("batch_prepare", "batch_submit", "batch_refresh", "batch_cancel", "batch_collect"):
        with pytest.raises(ValueError, match="saved batch for this engine"):
            invoke(s, action, engine="muferro/1", batch_id=batch)
    prepared_batch = invoke(s, "batch_prepare", batch_id=batch)
    assert prepared_batch["ok"] and s["client"].tasks() == []
    assert invoke(s, "batch_prepare", batch_id=batch)["ok"]
    assert len(s["client"].workspaces()) == 2
    assert invoke(s, "batch_submit", batch_id=batch)["ok"]
    assert invoke(s, "batch_submit", batch_id=batch)["ok"] and len(s["client"].tasks()) == 2
    assert invoke(s, "batch_refresh", batch_id=batch)["ok"]
    for task in s["client"].tasks():
        assert finish(s["client"], s["supervisor"], task["id"])["state"] == "succeeded"
    assert invoke(s, "batch_collect", batch_id=batch)["ok"]
    assert invoke(s, "batch_collect", batch_id=batch)["ok"]
    for item in prepared_batch["items"]:
        assert invoke(s, "view", run_id=item["run_id"])["qoi"]["density"] == pytest.approx(1.4)


def test_native_batch_run_reuses_tasks_and_cancel_is_explicit(native_runtime):
    s = native_runtime
    result = invoke(s, "batch_run", record_ids=s["rows"], connection=s["connection"], options=s["options"])
    assert result["ok"] and len(s["client"].tasks()) == 2
    assert invoke(s, "batch_run", record_ids=s["rows"], connection=s["connection"], options=s["options"])["id"] == result["id"]
    assert len(s["client"].tasks()) == 2
    assert invoke(s, "batch_cancel", batch_id=result["id"])["ok"]
    for task in s["client"].tasks():
        assert finish(s["client"], s["supervisor"], task["id"])["state"] == "cancelled"
    assert len(s["client"].tasks()) == 2


def test_muferro_fixed_dispatch_preserves_collector_and_domain_view(native_runtime, monkeypatch):
    s = native_runtime
    for name in ("STK_MUPRO_ENV_SCRIPTS", "MUPROROOT", "MUPRO_SDK_PREFIX"):
        monkeypatch.delenv(name, raising=False)
    sdk = make_fake_sdk(s["tmp"] / "fake-sdk")
    imported = invoke(s, "import", engine="muferro/1", source=str(sdk / "share/mupro/skills/mupro-muferro/examples"))
    cloned = invoke(s, "clone", engine="muferro/1", record_id=imported["record_id"])
    run = invoke(s, "prepare", engine="muferro/1", record_id=cloned["record_id"], connection=s["connection"],
                 options={"sdk_prefix": str(sdk), "launcher": "none"})
    assert s["client"].tasks() == []
    task_id = s["p"].runs.submit(run["id"])["status"]["task"]["id"]
    assert finish(s["client"], s["supervisor"], task_id)["state"] == "succeeded"
    collected = invoke(s, "collect", engine="muferro/1", run_id=run["id"])
    assert collected["table_id"] == muferro.RESULT_TABLE_ID and collected["qoi"]["total_energy"] == pytest.approx(-3.375)
    assert set(invoke(s, "logs", engine="muferro/1", run_id=run["id"])["streams"]) == {"stdout", "stderr"}
    opened = []
    monkeypatch.setattr(s["api"].viewer, "open", lambda path, **options: opened.append((path, options)) or "domain view")
    assert invoke(s, "view", engine="muferro/1", run_id=run["id"]) == "domain view"
    assert opened == [(Path(collected["directory"]), {"preset": "muferro-domains"})]
    assert len(s["client"].tasks()) == 1
