"""A real Runtime collects an explicitly synthetic HDF5 sidecar under the original task."""
from pathlib import Path

import pytest

h5py = pytest.importorskip("h5py")
np = pytest.importorskip("numpy")

from conftest import finish  # noqa: E402
from mupro_fake import make_fake_sdk  # noqa: E402
from suan.connectors.files import LocalFiles  # noqa: E402
from suan.connectors.mupro import MuFerroConnector  # noqa: E402
from suan.workflows.muferro import RESULT_TABLE_ID  # noqa: E402
from test_desktop_bridge_runtime import add_profile  # noqa: E402
from test_workflow_muferro import project, scripts, bridge_env, revision  # noqa: E402,F401


@pytest.mark.parametrize("mode", ["valid", "grid", "empty", "corrupt", "dtype", "components"])
def test_collect_hdf5_sidecar_is_verified_registered_and_not_resubmitted(project, scripts, runtime,
                                                                       tmp_path, monkeypatch, mode):
    api, p = project
    client, supervisor, _, _ = runtime
    connection = add_profile(scripts, runtime)
    sdk = make_fake_sdk(tmp_path / "synthetic-sdk")
    sidecar = tmp_path / "synthetic-run.h5"
    values = np.arange(4 * 3 * 2 * 3, dtype=np.float32).reshape(4, 3, 2, 3)
    if mode == "corrupt":
        sidecar.write_bytes(b"synthetic invalid HDF5")
    else:
        with h5py.File(sidecar, "w") as file:
            if mode != "empty":
                file.create_dataset("t00000002/Polar", data=np.ones((5, 3, 2, 3)) if mode == "grid" else values)
                if mode in {"dtype", "components"}:
                    file.create_dataset("t00000004/Polar", data=values.astype("float64") if mode == "dtype"
                                        else np.ones((4, 3, 2, 4), dtype="float32"))
    program = sdk / "bin/muFerro"
    text = program.read_text()
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
    if mode != "valid":
        with pytest.raises((ValueError, RuntimeError), match="HDF5|HDF|readable"):
            api.muferro.collect(run["id"])
        assert not any(table["id"] == RESULT_TABLE_ID for table in p.snapshot()["tables"])
        assert len(client.tasks()) == 1
        return
    collected = api.muferro.collect(run["id"])
    assert any(file["path"].endswith("/case/run.h5") for file in collected["files"])
    assert (Path(collected["directory"]) / "run.h5").read_bytes() == sidecar.read_bytes()
    assert api.muferro.collect(run["id"]) == collected
    connector, source = MuFerroConnector(), LocalFiles(collected["directory"])
    image = connector.open(source, "hdf5:Polar").read(frame={"first": True})
    np.testing.assert_array_equal(image.array("Polar"), values.transpose(2, 1, 0, 3))
    assert image.array("Polar").dtype == np.dtype("float32")
    assert len(client.tasks()) == 1
    with open(Path(collected["directory"]) / "run.h5", "ab") as file:
        file.write(b"changed")
    with pytest.raises(ValueError, match="changed locally"):
        api.muferro.collect(run["id"])
    assert len(client.tasks()) == 1
