"""A synthetic Runtime run verifies collected frame selection through the Viewer preset."""
import hashlib
import os
import shutil
from pathlib import Path

import pytest

from conftest import finish
from mupro_fake import make_fake_sdk
from suan.data.dat import read_dat
from suan.graph import catalog
from suan.graph.schema import GraphError
from suan.graph.service import MemoryBlobSink, evaluate_request
from suan.workflows.muferro import native_action
from test_desktop_bridge_runtime import add_profile
from test_workflow_muferro import bridge_env, project, revision, scripts  # noqa: F401


def _collected_run(project, scripts, runtime, tmp_path, monkeypatch):
    """A real synthetic Runtime task collected by MuFerro: no licensed program, no native window."""
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
    return api, p, client, run, task_id, collected


def _viewer(tmp_path, cache):
    """The Viewer stand-in: the real graph service over the dispatched directory.

    Bind the source-owned proof exactly as the desktop graph worker does.
    """
    def open_viewer(path, *, preset, parameters=None, source_proof=None):
        from suan.graph.collected import local_resolver
        resolver = local_resolver({"run": path}, {"run": source_proof} if source_proof is not None else None)
        return evaluate_request({"preset": preset, "outputs": ["fractions"], "parameters": parameters or {}},
                                resolver=resolver, cache_dir=tmp_path / cache,
                                blob_sink=MemoryBlobSink(), registry=catalog.build_registry(entry_points=False))
    return open_viewer


def _view(api, p, run):
    return native_action(api, "view", {"project_id": p.snapshot()["project"]["id"], "run_id": run["id"]})


def test_collected_latest_frame_survives_view(project, scripts, runtime, tmp_path, monkeypatch):
    api, p, client, run, task_id, collected = _collected_run(project, scripts, runtime, tmp_path, monkeypatch)
    root = Path(collected["directory"])
    latest = root / "Polar.00000002.dat"
    initial = root / "Polar.00000000.dat"
    assert latest.stat().st_size != initial.stat().st_size
    digest = hashlib.sha256(latest.read_bytes()).hexdigest()
    assert next(f for f in client.artifacts(task_id) if f["path"] == "case/" + latest.name)["sha256"] == digest
    assert next(f for f in collected["files"] if f["path"].endswith(latest.name))["sha256"] == digest
    assert read_dat(latest)[0, 0, 0, 0] == 1113
    assert read_dat(initial)[0, 0, 0, 0] == 1111

    open_viewer = _viewer(tmp_path, "graph")
    live = open_viewer(root, preset="muferro-domains")
    assert live["parameters"]["step"] == {"value": 0, "choices": [0]}

    monkeypatch.setattr(api.viewer, "open", open_viewer)
    displayed = _view(api, p, run)
    assert displayed["parameters"]["step"] == {"value": 2, "choices": [0, 2]}

    presets = {preset["id"]: preset["graph"] for preset in scripts.call("graph.presets")["presets"]}
    assert presets["muferro-domains"]["nodes"][0]["params"] == {"binding": "run"}
    assert presets["muferro-collected-domains"]["nodes"][0]["params"] == {"binding": "run", "live": False}

    monkeypatch.setattr(api.graph, "presets", lambda: [{"id": "muferro-domains"}])
    fallback = _view(api, p, run)
    assert fallback["parameters"]["step"] == live["parameters"]["step"]


def _flip_half_z(data):
    """A valid different Polar frame of identical size: negate P_z where x <= 2 (sign takes the pad column)."""
    lines = data.split(b"\n")
    for n, line in enumerate(lines[1:], 1):
        fields = line.split()
        if len(fields) == 5 and fields[3] == b"3" and int(fields[0]) <= 2:
            assert line[-15:-14] == b" " and line[-14:-13].isdigit()
            lines[n] = line[:-15] + b"-" + line[-14:]
    changed = b"\n".join(lines)
    assert len(changed) == len(data) and changed != data
    return changed


def _counts(result):
    table = result["outputs"]["fractions"]["columns"]
    return {name: count for name, count in zip(table["name"], table["count"]) if count}


def test_collected_view_refuses_frame_replaced_at_viewer_dispatch(project, scripts, runtime, tmp_path, monkeypatch):
    """After View checked the saved manifest, the registered latest DAT is replaced before the Viewer reads it.

    The replacement is a valid frame of identical size with the original mtime, so only a
    content-bound source proof can tell it apart from the collected file.
    """
    api, p, client, run, task_id, collected = _collected_run(project, scripts, runtime, tmp_path, monkeypatch)
    root = Path(collected["directory"])
    latest = root / "Polar.00000002.dat"
    original = latest.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    registered = next(f for f in collected["files"] if f["path"].endswith(latest.name))
    assert registered["sha256"] == digest
    stat = latest.stat()
    tasks = len(client.tasks())

    open_viewer = _viewer(tmp_path, "graph")
    monkeypatch.setattr(api.viewer, "open", open_viewer)
    clean = _view(api, p, run)  # primes the clean graph cache
    assert clean["parameters"]["step"] == {"value": 2, "choices": [0, 2]}
    assert hashlib.sha256(latest.read_bytes()).hexdigest() == digest

    replaced = _flip_half_z(original)
    changed_digest = hashlib.sha256(replaced).hexdigest()
    assert changed_digest != digest
    # The replacement is scientifically different: evaluated alone (own directory and cache) it
    # classifies other domains than the collected frame.
    scratch = tmp_path / "replacement-case"
    shutil.copytree(root, scratch)
    (scratch / latest.name).write_bytes(replaced)
    assert read_dat(scratch / latest.name)[0, 0, 0, 2] == -read_dat(latest)[0, 0, 0, 2]
    alone = _viewer(tmp_path, "replacement-graph")(scratch, preset="muferro-collected-domains")
    assert alone["parameters"]["step"] == {"value": 2, "choices": [0, 2]}
    assert _counts(clean) == {"O[011]": 18, "R[111]": 6}
    assert _counts(alone) == {"O[011]": 8, "O[01-1]": 10, "R[111]": 4, "R[11-1]": 2}

    def write(path, data):
        path.write_bytes(data)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        assert path.stat().st_size == stat.st_size and path.stat().st_mtime_ns == stat.st_mtime_ns

    dispatched = []

    def replace_at_dispatch(path, *, preset, parameters=None, **proof):
        assert Path(path) == root and preset == "muferro-collected-domains"
        write(latest, replaced)
        dispatched.append(sorted(proof))
        return open_viewer(path, preset=preset, parameters=parameters, **proof)

    monkeypatch.setattr(api.viewer, "open", replace_at_dispatch)
    accepted = []
    for attempt in ("cold", "warm"):
        if attempt == "warm":
            assert _counts(open_viewer(scratch, preset="muferro-collected-domains")) == _counts(alone)
        try:
            result = _view(api, p, run)
        except (ValueError, GraphError):
            continue  # refused; a TypeError from an unaccepted proof keyword is not a refusal
        finally:
            write(latest, original)  # each attempt starts from the collected bytes
        accepted.append((attempt, result["parameters"]["step"], _counts(result), result["cache"]))
    assert len(dispatched) == 2

    # Explicit restore: the original bytes open the original frame and result, with no new task.
    monkeypatch.setattr(api.viewer, "open", open_viewer)
    assert hashlib.sha256(latest.read_bytes()).hexdigest() == digest
    restored = _view(api, p, run)
    assert restored["parameters"]["step"] == clean["parameters"]["step"]
    assert restored["outputs"]["fractions"] == clean["outputs"]["fractions"]
    assert len(client.tasks()) == tasks

    assert not accepted, (f"View delivered {changed_digest[:12]} for registered {digest[:12]} "
                          f"(forwarded proof keys {dispatched}): {accepted}; clean {_counts(clean)}")
