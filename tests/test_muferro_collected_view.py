"""A synthetic Runtime run verifies collected frame selection through the Viewer preset."""
import hashlib
from pathlib import Path

import pytest

from conftest import finish
from mupro_fake import make_fake_sdk
from suan.data.dat import read_dat
from suan.graph import catalog
from suan.graph.resolve import LocalDirResolver
from suan.graph.service import MemoryBlobSink, evaluate_request
from suan.workflows.muferro import native_action
from test_desktop_bridge_runtime import add_profile
from test_workflow_muferro import bridge_env, project, revision, scripts  # noqa: F401


def test_collected_latest_frame_survives_view(project, scripts, runtime, tmp_path, monkeypatch):
    pytest.importorskip("numpy")
    api, p = project
    client, supervisor, _, _ = runtime
    connection = add_profile(scripts, runtime)
    sdk = make_fake_sdk(tmp_path / "synthetic-sdk", steps=2, interval=2)
    program = sdk / "bin/muFerro"
    old = "sys.exit(fake_muferro('ok'))"
    text = program.read_text()
    assert text.count(old) == 1
    program.write_text(text.replace(old, """exit_code = fake_muferro('ok')
from pathlib import Path
latest = Path("Polar.00000002.dat")
latest.write_bytes(b"\\n".join(line.rstrip() for line in latest.read_bytes().splitlines()) + b"\\n")
sys.exit(exit_code)
"""))
    for name in ("STK_MUPRO_ENV_SCRIPTS", "MUPROROOT", "STK_MUPRO_ALLOW_LOCAL_MPI",
                 "STK_ALLOW_LOCAL_MPI", "SLURM_JOB_ID", "PBS_JOBID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MUPRO_SDK_PREFIX", str(sdk))
    row = api.muferro.import_case(sdk / "share/mupro/skills/mupro-muferro/examples",
                                 expected_revision=revision(p))["record_id"]
    run = api.muferro.prepare(row, connection, expected_revision=revision(p), launcher="none")
    task_id = p.runs.submit(run["id"])["status"]["task"]["id"]
    assert finish(client, supervisor, task_id)["state"] == "succeeded"
    collected = api.muferro.collect(run["id"])
    assert collected["qoi"] == {"total_energy": -2.25, "step": 2}
    root = Path(collected["directory"])
    latest = root / "Polar.00000002.dat"
    initial = root / "Polar.00000000.dat"
    assert latest.stat().st_size != initial.stat().st_size
    digest = hashlib.sha256(latest.read_bytes()).hexdigest()
    assert next(f for f in client.artifacts(task_id) if f["path"] == "case/" + latest.name)["sha256"] == digest
    assert next(f for f in collected["files"] if f["path"].endswith(latest.name))["sha256"] == digest
    assert read_dat(latest)[0, 0, 0, 0] == 1113
    assert read_dat(initial)[0, 0, 0, 0] == 1111

    def open_viewer(path, *, preset, parameters=None):
        return evaluate_request({"preset": preset, "outputs": ["fractions"], "parameters": parameters or {}},
                                resolver=LocalDirResolver({"run": path}), cache_dir=tmp_path / "graph",
                                blob_sink=MemoryBlobSink(), registry=catalog.build_registry(entry_points=False))

    live = open_viewer(root, preset="muferro-domains")
    assert live["parameters"]["step"] == {"value": 0, "choices": [0]}

    monkeypatch.setattr(api.viewer, "open", open_viewer)
    displayed = native_action(api, "view", {"project_id": p.snapshot()["project"]["id"], "run_id": run["id"]})
    assert displayed["parameters"]["step"] == {"value": 2, "choices": [0, 2]}

    presets = {preset["id"]: preset["graph"] for preset in scripts.call("graph.presets")["presets"]}
    assert presets["muferro-domains"]["nodes"][0]["params"] == {"binding": "run"}
    assert presets["muferro-collected-domains"]["nodes"][0]["params"] == {"binding": "run", "live": False}

    monkeypatch.setattr(api.graph, "presets", lambda: [{"id": "muferro-domains"}])
    fallback = native_action(api, "view", {"project_id": p.snapshot()["project"]["id"], "run_id": run["id"]})
    assert fallback["parameters"]["step"] == live["parameters"]["step"]
