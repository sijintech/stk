"""A real Runtime collects an explicitly synthetic HDF5 sidecar under the original task."""
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

h5py = pytest.importorskip("h5py")
np = pytest.importorskip("numpy")

from conftest import finish  # noqa: E402
from mupro_fake import make_fake_sdk  # noqa: E402
from suan.connectors.files import LocalFiles  # noqa: E402
from suan.connectors.mupro import MuFerroConnector  # noqa: E402
from suan.desktop_bridge.workflow_runs import WorkflowRunExecutor, _Job  # noqa: E402
from suan.graph.catalog import load_preset  # noqa: E402
from suan.project import ProjectError, ProjectStore  # noqa: E402
from suan.render.payload import decode  # noqa: E402
from suan.workflows.muferro import RESULT_FIELD_IDS, RESULT_TABLE_ID, native_action  # noqa: E402
from test_desktop_bridge import BridgeCallError  # noqa: E402
from test_desktop_bridge_runtime import add_profile  # noqa: E402
from test_workflow_muferro import project, scripts, bridge_env, revision  # noqa: E402,F401


SELECTOR = "t00000002/Polar"
_POSIX_LINKS = pytest.mark.skipif(os.name == "nt" or not hasattr(os, "symlink"),
                                 reason="the case-directory swap uses a POSIX directory symlink")


def _synthetic_hdf5_run(project, scripts, runtime, tmp_path, monkeypatch, sidecar):
    """Prepare, submit and finish one synthetic MuFerro task whose solver publishes ``sidecar`` as run.h5."""
    api, p = project
    client, supervisor, _, _ = runtime
    connection = add_profile(scripts, runtime)
    sdk = make_fake_sdk(tmp_path / "synthetic-sdk", steps=4)
    program = sdk / "bin/muFerro"
    text = program.read_text()
    assert text.count("sys.exit(fake_muferro('ok'))") == 1
    text = text.replace("sys.exit(fake_muferro('ok'))",
                        "result = fake_muferro('ok')\nimport shutil\n"
                        f"shutil.copyfile({str(sidecar)!r}, 'run.h5')\nsys.exit(result)")
    program.write_text(text)
    for name in ("STK_MUPRO_ENV_SCRIPTS", "MUPROROOT", "STK_MUPRO_ALLOW_LOCAL_MPI",
                 "STK_ALLOW_LOCAL_MPI", "SLURM_JOB_ID", "PBS_JOBID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MUPRO_SDK_PREFIX", str(sdk))
    row = api.muferro.import_case(sdk / "share/mupro/skills/mupro-muferro/examples",
                                 expected_revision=revision(p))["record_id"]
    run = api.muferro.prepare(row, connection, expected_revision=revision(p), launcher="none")
    task_id = p.runs.submit(run["id"])["status"]["task"]["id"]
    assert finish(client, supervisor, task_id)["state"] == "succeeded"
    return run, task_id


@pytest.mark.parametrize("mode", ["valid", "grid", "empty", "corrupt", "dtype", "components"])
def test_collect_hdf5_sidecar_is_verified_registered_and_not_resubmitted(project, scripts, runtime,
                                                                       tmp_path, monkeypatch, mode):
    api, p = project
    client = runtime[0]
    sidecar = tmp_path / "synthetic-run.h5"
    values = np.arange(4 * 3 * 2 * 3, dtype=np.float32).reshape(4, 3, 2, 3)
    if mode == "corrupt":
        sidecar.write_bytes(b"synthetic invalid HDF5")
    else:
        with h5py.File(sidecar, "w") as file:
            if mode != "empty":
                file.create_dataset("t00000002/Polar", data=np.ones((5, 3, 2, 3)) if mode == "grid" else values)
                if mode == "valid":  # A later explicit step makes the frozen analysis selector discriminating.
                    file.create_dataset("t00000004/Polar", data=values + 100)
                if mode in {"dtype", "components"}:
                    file.create_dataset("t00000004/Polar", data=values.astype("float64") if mode == "dtype"
                                        else np.ones((4, 3, 2, 4), dtype="float32"))
    run, _ = _synthetic_hdf5_run(project, scripts, runtime, tmp_path, monkeypatch, sidecar)
    if mode != "valid":
        with pytest.raises((ValueError, RuntimeError), match="HDF5|HDF|readable"):
            api.muferro.collect(run["id"])
        assert not any(table["id"] == RESULT_TABLE_ID for table in p.snapshot()["tables"])
        assert len(client.tasks()) == 1
        return
    collected = api.muferro.collect(run["id"])
    assert any(file["path"].endswith("/case/run.h5") for file in collected["files"])
    assert (Path(collected["directory"]) / "run.h5").read_bytes() == sidecar.read_bytes()
    report_path = Path(collected["directory"]).parent / "stk-mupro.json"
    report = json.loads(report_path.read_bytes())
    digest = report["program"]["sha256"]
    forged = "0" * 64 if digest != "0" * 64 else "1" * 64
    original_read_text = Path.read_text

    def substitute_on_reopen(candidate, *args, **kwargs):
        if candidate == report_path:
            report["program"]["sha256"] = forged
            candidate.write_text(json.dumps(report), encoding="utf-8")
        return original_read_text(candidate, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", substitute_on_reopen)
        assert api.muferro.collect(run["id"]) == collected
    table = next(table for table in p.snapshot()["tables"] if table["id"] == RESULT_TABLE_ID)
    assert table["records"][0]["values"][RESULT_FIELD_IDS["program"]] == digest

    connector, source = MuFerroConnector(), LocalFiles(collected["directory"])
    image = connector.open(source, "hdf5:Polar").read(frame={"first": True})
    np.testing.assert_array_equal(image.array("Polar"), values.transpose(2, 1, 0, 3))
    assert image.array("Polar").dtype == np.dtype("float32")
    assert len(client.tasks()) == 1
    _assert_collected_analysis(p, collected, sidecar.read_bytes(), values)
    assert len(client.tasks()) == 1
    path = Path(collected["directory"]) / "run.h5"
    opened = []
    monkeypatch.setattr(api.viewer, "open", lambda folder, *, preset: opened.append((folder, preset)))
    params = {"project_id": p.snapshot()["project"]["id"], "run_id": run["id"]}
    native_action(api, "view", params)
    assert opened == [(path.parent, "muferro-collected-domains")]

    path.unlink()
    if hasattr(os, "mkfifo"):
        os.mkfifo(path)
        original_open = Path.open

        def guard_fifo(candidate, *args, **kwargs):
            if candidate == path:
                pytest.fail("View tried a blocking open on the result FIFO")
            return original_open(candidate, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(Path, "open", guard_fifo)
            with pytest.raises(ValueError, match="changed locally"):
                native_action(api, "view", params)
        path.unlink()
    if hasattr(os, "symlink") and os.name != "nt":
        alias = path.parent / "duplicate-sidecar.h5"
        alias.write_bytes(sidecar.read_bytes())
        path.symlink_to(alias)
        with pytest.raises(ValueError, match="changed locally"):
            native_action(api, "view", params)
        with pytest.raises(ValueError, match="must not be symbolic links"):
            api.muferro.collect(run["id"])
        path.unlink()
    with pytest.raises(ValueError, match="changed locally"):
        native_action(api, "view", params)
    assert opened == [(path.parent, "muferro-collected-domains")]

    path.write_bytes(sidecar.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="changed locally"):
        api.muferro.collect(run["id"])
    assert len(client.tasks()) == 1


def _saved_hdf5_view(selector, expected_sha256):
    graph = load_preset("scalar-volume")
    graph["parameters"] = [p for p in graph["parameters"] if p["name"] != "path"]
    source = next(node for node in graph["nodes"] if node["id"] == "src")
    source.update(type="stk.source.mupro_hdf5@1", params={"binding": "data", "path": "run.h5",
                                                          "selector": selector, "expected_sha256": expected_sha256})
    return {"format": "stk.analysis-document/1", "graph": graph,
            "parameters": {"field": "Polar", "component": 0}, "outputs": ["view"]}


def _run_saved(p, document, snapshot_id, record_id):
    analysis_id, run_id = str(uuid4()), str(uuid4())
    p.analyses.create("Collected MuFerro HDF5", document, analysis_id=analysis_id, expected_revision=revision(p))
    run = p.analysis_runs.prepare(analysis_id, snapshot_id, {"data": {"run.h5": record_id}},
                                  run_id=run_id, expected_revision=revision(p))
    assert p.analysis_runs.start(run_id)["status"] in {"running", "succeeded", "failed"}
    deadline = time.monotonic() + 60
    while (final := p.analysis_runs.get(run_id))["status"] in {"prepared", "running"}:
        assert time.monotonic() < deadline, final
        time.sleep(0.05)
    return run, final


def _assert_collected_analysis(p, collected, sidecar_bytes, values):
    """The exact collected run.h5 record, frozen and read through the strict bridge's GraphWorker."""
    recorded = next(file for file in collected["files"] if file["path"].endswith("/case/run.h5"))
    assert recorded["sha256"] == hashlib.sha256(sidecar_bytes).hexdigest()
    table = next(table for table in p.snapshot()["tables"] if table["id"] == RESULT_TABLE_ID)
    assert recorded in table["records"][0]["values"][RESULT_FIELD_IDS["files"]]
    files_before = p.files.list()["records"]
    matches = [row for row in files_before if row["path"] == recorded["path"]]
    assert len(matches) == 1 and matches[0]["location"] == "project"
    record_id = matches[0]["id"]
    snapshot = p.snapshots.capture([record_id], expected_revision=revision(p))["snapshot"]
    assert [(f["record_id"], f["path"], f["sha256"]) for f in snapshot["manifest"]["files"]] == [
        (record_id, recorded["path"], recorded["sha256"])]

    selector = "/t00000004/Polar"
    forged = "0" * 64 if recorded["sha256"] != "0" * 64 else "1" * 64
    original = Path(collected["directory"]) / "run.h5"
    moved = original.rename(original.with_name("run.h5.before-analysis"))
    try:
        run, final = _run_saved(p, _saved_hdf5_view(selector, recorded["sha256"]), snapshot["id"], record_id)
        _, refused = _run_saved(p, _saved_hdf5_view(selector, forged), snapshot["id"], record_id)
    finally:
        moved.rename(original)
    assert run["bindings"]["data"]["run.h5"] == {"record_id": record_id, "sha256": recorded["sha256"],
                                                 "size": len(sidecar_bytes)}
    assert final["status"] == "succeeded" and final["result"]["has_payload"] is True, final
    output = p.analysis_runs.result(run["id"])
    assert "src" in output["result"]["evaluated"]
    manifest = output["result"]["outputs"]["view"]["manifest"]
    blobs = {b["sha256"]: (Path(output["blob_dir"]) / b["sha256"][:2] / b["sha256"]).read_bytes()
             for b in manifest["buffers"]}
    payload = decode(manifest, blobs)
    volume = payload.layer("volume")
    assert volume["grid"]["dimensions"] == [4, 3, 2]  # x, y, z extent of the frozen case grid
    assert (volume["name"], volume["quantity"], volume["unit"]) == ("Polar_x", "polarization", "unspecified")
    assert volume["value_range"] == [100.0, 169.0]  # step 4; step 2 spans [0, 69]
    data = payload.array(volume["data"])
    assert data.dtype == np.dtype("float32")
    np.testing.assert_array_equal(data, (values + 100)[..., 0].transpose(2, 1, 0).ravel())

    assert (refused["status"], refused["result"], refused["error"]["code"]) == ("failed", None, "graph_error")
    assert "expected SHA-256" in refused["error"]["message"]
    assert p.files.list()["records"] == files_before


@pytest.mark.parametrize("fault", ["bytes", pytest.param("relink", marks=_POSIX_LINKS)])
def test_workflow_snapshot_refuses_changed_hdf5_after_collection(tmp_path, monkeypatch, fault):
    store = ProjectStore.create(tmp_path / "project", "Collected HDF5 snapshot")
    simulation_id, workflow_id, row_id, result_id = (str(uuid4()) for _ in range(4))
    relative = f"results/muferro/{simulation_id}/case/run.h5"
    output = store.directory / relative
    output.parent.mkdir(parents=True)
    selector = "t00000001/Polar"
    with h5py.File(output, "w") as file:
        file.create_dataset(selector, data=np.ones((2, 2, 2, 3), dtype=np.float32))
    verified = output.read_bytes()
    digest = hashlib.sha256(verified).hexdigest()

    replaced = False
    restore = None

    def collect(run_id, *, project):
        nonlocal replaced, restore
        assert run_id == simulation_id and project is store
        if fault == "relink" and not replaced:
            replaced = True
            restore = _link_case_elsewhere(output.parent, tmp_path / "outside-case")
        return {"record_id": result_id, "files": [{"path": relative, "sha256": digest}]}

    def after_index(_project):
        nonlocal replaced
        if fault == "bytes" and not replaced:
            replaced = True
            with h5py.File(output, "r+") as file:
                file[selector][...] = 9.0

    api = SimpleNamespace(project=store, muferro=SimpleNamespace(collect=collect))
    executor = WorkflowRunExecutor(None, scripting=lambda *_: api, changed=after_index)
    # Model an admitted collection. A None reply now means a durable cancel blocked it.
    monkeypatch.setattr(executor, "_progress", lambda *args, **kwargs: {"status": "running"})
    job = _Job(store, workflow_id)
    plan = {"steps": {"simulation": {"template": "muferro/1"}}}
    row = {"id": row_id}
    run = {"id": simulation_id, "status": {"task": {"id": "c" * 32}}}

    with pytest.raises(ProjectError, match="expected SHA-256" if fault == "bytes" else "directories"):
        executor._collect(job, plan, "simulation", row, 1, run)
    assert replaced and store.snapshots.list()["snapshots"] == []
    assert store.info()["revision"] == (1 if fault == "bytes" else 0)
    assert all(record["location"] == "project" for record in store.files.list()["records"])
    assert not list((store.directory / ".stk/objects/sha256").glob("*/*"))
    assert not list((store.directory / ".stk/tmp").glob("*"))

    if restore is None:
        output.write_bytes(verified)
    else:
        restore()
    produced = executor._collect(job, plan, "simulation", row, 1, run)
    file_id = produced["files"]["case/run.h5"]
    frozen = store.snapshots.resolve(produced["snapshot_id"], file_id)
    assert produced["result_record_id"] == result_id
    assert Path(frozen["path"]).read_bytes() == verified
    assert len(store.snapshots.list()["snapshots"]) == 1


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _tamper_at_first_registration(patch, files_type, root, tamper, *, after_index=False):
    """Change run.h5 just before or after its managed index batch."""
    fired, original_index = [], files_type.index

    def index(self, paths, **kwargs):
        target = next((Path(path) for path in paths if Path(path).name == "run.h5"), None)
        if target is None or fired:
            return original_index(self, paths, **kwargs)
        target = root / target
        result = original_index(self, paths, **kwargs) if after_index else None
        fired.append(target)
        tamper(target)
        return result if after_index else original_index(self, paths, **kwargs)
    patch.setattr(files_type, "index", index)
    return fired


def _same_size_same_mtime(path, original, write):
    """Change one voxel with ``write``, keep the size and restore the mtime; return the byte restorer."""
    before = path.stat()
    write(path)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    after, changed = path.stat(), path.read_bytes()
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)
    assert _sha256(changed) != _sha256(original)

    def restore():
        path.write_bytes(original)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    return restore


def _overwrite_voxel(path):
    with h5py.File(path, "r+") as file:
        file[SELECTOR][0, 0, 0, 0] = 999


def _replace_with_changed_copy(swap):
    def write(path):
        shutil.copyfile(path, swap)
        _overwrite_voxel(swap)
        os.replace(swap, path)  # a new file; the caller restores the verified mtime
    return write


def _link_case_elsewhere(case, outside):
    """Move the owned case directory aside and put a link to a byte-identical tree outside the project in its place."""
    shutil.copytree(case, outside)
    displaced = case.rename(case.with_name("displaced-case"))
    case.symlink_to(outside, target_is_directory=True)

    def restore():
        case.unlink()  # the link only; the outside tree stays untouched
        displaced.rename(case)
    return restore


def _assert_registered_verified_bytes(p, collected, run_id, task_id, original, values):
    """The returned files, result row, project Files record and normal reads all name the verified run.h5."""
    recorded = next(file for file in collected["files"] if file["path"].endswith("/case/run.h5"))
    assert recorded == {"path": f"results/muferro/{run_id}/case/run.h5", "sha256": _sha256(original)}
    table = next(table for table in p.snapshot()["tables"] if table["id"] == RESULT_TABLE_ID)
    [row] = table["records"]
    assert row["values"][RESULT_FIELD_IDS["task"]] == task_id
    assert recorded in row["values"][RESULT_FIELD_IDS["files"]]
    files = p.files.list()["records"]
    assert [(r["location"], r["path"]) for r in files if r["location"] != "project"] == []
    [record] = [r for r in files if r["path"] == recorded["path"]]
    assert (record["location"], record["state"], record["size"]) == ("project", "present", len(original))
    frozen = p.snapshots.capture([record["id"]], expected_revision=revision(p))["snapshot"]
    assert [(f["path"], f["sha256"]) for f in frozen["manifest"]["files"]] == [(recorded["path"], _sha256(original))]
    with h5py.File(p.snapshots.resolve(frozen["id"], record["id"])["path"], "r") as file:
        np.testing.assert_array_equal(file[SELECTOR][...], values)
    image = MuFerroConnector().open(LocalFiles(collected["directory"]), "hdf5:Polar").read(frame={"first": True})
    np.testing.assert_array_equal(image.array("Polar"), values.transpose(2, 1, 0, 3))


@pytest.mark.parametrize("mode", ["control", "rewrite", "replace", "late", pytest.param("relink", marks=_POSIX_LINKS)])
def test_collect_registers_only_the_verified_hdf5_bytes(project, scripts, runtime, tmp_path, monkeypatch, mode):
    """A same-size, same-mtime change or a case-directory link swap during registration is refused; restore and retry."""
    api, p = project
    client, server = runtime[0], runtime[2]
    submissions, cancels = [], []
    submit, cancel = server.service.submit, server.service.cancel

    def record_submit(spec, key):
        submissions.append(key)
        return submit(spec, key)

    def record_cancel(task_id):
        cancels.append(task_id)
        return cancel(task_id)
    monkeypatch.setattr(server.service, "submit", record_submit)
    monkeypatch.setattr(server.service, "cancel", record_cancel)
    sidecar = tmp_path / "synthetic-run.h5"
    values = np.arange(4 * 3 * 2 * 3, dtype=np.float32).reshape(4, 3, 2, 3)
    with h5py.File(sidecar, "w") as file:
        file.create_dataset(SELECTOR, data=values)
    original = sidecar.read_bytes()
    run, task_id = _synthetic_hdf5_run(project, scripts, runtime, tmp_path, monkeypatch, sidecar)
    root = Path(next(item["directory"] for item in api.projects.list() if item["handle"] == p.handle))
    assert (len(submissions), cancels) == (1, [])
    restorers = []

    def tamper(path):
        assert path.read_bytes() == original  # collection has already verified these bytes
        if mode in {"rewrite", "late"}:
            restorers.append(_same_size_same_mtime(path, original, _overwrite_voxel))
        elif mode == "replace":
            restorers.append(_same_size_same_mtime(path, original, _replace_with_changed_copy(tmp_path / "swap.h5")))
        elif mode == "relink":
            restorers.append(_link_case_elsewhere(path.parent, tmp_path / "outside-case"))

    with monkeypatch.context() as patch:
        fired = _tamper_at_first_registration(patch, type(p.files), root, tamper, after_index=mode == "late")
        try:
            collected, error = api.muferro.collect(run["id"]), None
        except (BridgeCallError, ValueError, RuntimeError) as exc:
            collected, error = None, exc
    assert len(fired) == 1, "collection no longer reached the injected registration seam; retarget it"
    if mode == "control":
        assert error is None
        _assert_registered_verified_bytes(p, collected, run["id"], task_id, original, values)
        assert (len(submissions), cancels, len(client.tasks())) == (1, [], 1)
        return

    observed = {
        "rejected": error is not None,
        "result_rows": [row["id"] for table in p.snapshot()["tables"] if table["id"] == RESULT_TABLE_ID
                        for row in table["records"]],
        "external_files": [(r["location"], r["path"]) for r in p.files.list()["records"] if r["location"] != "project"],
        "submissions": len(submissions), "cancels": len(cancels), "tasks": len(client.tasks()),
    }
    assert observed == {"rejected": True, "result_rows": [], "external_files": [],
                        "submissions": 1, "cancels": 0, "tasks": 1}, (observed, collected)
    if mode == "late":
        assert isinstance(error, ProjectError) and "digest changed" in str(error)
    else:
        assert isinstance(error, BridgeCallError) and error.code == "invalid_params"

    [restore] = restorers
    restore()
    retried = api.muferro.collect(run["id"])
    _assert_registered_verified_bytes(p, retried, run["id"], task_id, original, values)
    assert (len(submissions), cancels, len(client.tasks())) == (1, [], 1)
