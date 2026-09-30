"""Offline acceptance example uses the real isolated kernel, bridge and table graph worker."""
import csv
import hashlib
import json
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace

import pytest

from examples.project_analysis import offline
from suan.project import ProjectStore
from test_desktop_bridge import bridge_env  # noqa: F401
from test_desktop_scripts import scripts, settled  # noqa: F401


def test_real_file_execution_builds_one_frozen_table_run_without_touching_the_selected_project(scripts, tmp_path):  # noqa: F811
    pytest.importorskip("numpy")
    old_directory = tmp_path / "existing"
    old = scripts.call("project.create", {"directory": str(old_directory), "name": "Existing work"})["project"]
    scripts.call("project.apply", {"handle": old["handle"], "expected_revision": 0,
                                  "commands": [{"op": "create_table", "name": "Keep this"}]})
    previous = ProjectStore(old_directory)
    before, history = previous.snapshot(), previous.history()
    session = scripts.call("script.open", {"directory": str(tmp_path)})["session"]
    directory = tmp_path / "离线分析 demo"
    wrapper = tmp_path / "run_acceptance.py"
    wrapper.write_text(dedent(f'''\
        from copy import deepcopy
        import json
        from pathlib import Path
        from examples.project_analysis.offline import create_demo, REQUIRED_OPERATIONS
        from suan.scripting import API

        selected_before = stk.project.snapshot()
        selected_history = stk.project.history()
        calls = []
        def audited(operation, params):
            assert operation in REQUIRED_OPERATIONS | {{"operations"}}, operation
            calls.append((operation, deepcopy(params)))
            if operation == "project.analysis_runs.start":
                persisted = json.loads((Path({str(directory)!r}) / "demo.json").read_text(encoding="utf-8"))
                assert persisted["run_id"] == params["run_id"]
                assert persisted["synthetic"] is True
                assert persisted["plan_sha256"]
            return stk.call(operation, **params)

        demo = create_demo(API(audited), {str(directory)!r}, wait_seconds=30)
        assert demo["verified_result"] is True and demo["status"] == "succeeded"
        assert not demo["observation_timed_out"]
        methods = [method for method, _ in calls]
        assert methods.count("project.analysis_runs.prepare") == 1
        assert methods.count("project.analysis_runs.start") == 1
        assert methods.count("project.analysis_runs.result") == 1
        assert not any(method.startswith(("ui.", "runtime.", "graph.", "connection.", "model.")) for method in methods)
        assert stk.project.snapshot() == selected_before
        assert stk.project.history() == selected_history
        assert stk.project.handle == {old['handle']!r}
        p = stk.projects.open(demo["directory"], expected_id=demo["project_id"])
        assert p.runs.list()["runs"] == []
        assert p.requests.list()["requests"] == []
        assert len(p.analysis_runs.list()["runs"]) == 1
        assert p.snapshots.verify(demo["snapshot_id"])["ok"]
    '''), encoding="utf-8")
    launched = scripts.call("script.execute", {"session": session, "path": str(wrapper), "project_handle": old["handle"]})
    completed = settled(scripts, session, timeout=60)
    assert completed["run"]["id"] == launched["run"]
    assert completed["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    log = scripts.call("script.read", {"session": session})["text"]
    assert "73 rows × 10 columns" in log and "Open this NEW project manually" in log
    assert previous.snapshot() == before and previous.history() == history
    assert scripts.events_of("ui.request") == [] and not scripts.violations

    note = json.loads((directory / "demo.json").read_text(encoding="utf-8"))
    store = ProjectStore(directory)
    assert store.info()["revision"] == note["revision"] == 3
    assert len(store.history()) == 3
    runs = store.analysis_runs.list()["runs"]
    assert len(runs) == 1 and runs[0]["id"] == note["run_id"] and runs[0]["status"] == "succeeded"
    frozen = store.analysis_runs.get(note["run_id"])
    assert frozen["document"]["outputs"] == ["table"]
    assert frozen["document"]["parameters"] == {"path": "synthetic.csv"}
    assert frozen["bindings"]["data"]["synthetic.csv"]["record_id"] == note["record_id"]
    assert frozen["bindings"]["data"]["synthetic.csv"]["sha256"] == hashlib.sha256((directory / "synthetic.csv").read_bytes()).hexdigest()
    archive_path = directory / frozen["result"]["directory"] / "graph-result.json"
    archive_bytes = archive_path.read_bytes()
    assert hashlib.sha256(archive_bytes).hexdigest() == frozen["result"]["manifest_sha256"]
    archive = json.loads(archive_bytes)
    returned = archive["outputs"]["table"]
    expected_names = ["step", "temperature_difference", "case", *[f"sample_{index}" for index in range(1, 8)]]
    assert returned["column_names"] == expected_names and "blob" not in returned
    assert not archive.get("errors") and frozen["result"]["has_payload"] is False
    columns = returned["columns"]
    assert columns["step"] == list(range(73)) and all(type(value) is int for value in columns["step"])
    assert columns["temperature_difference"] == [-9.5, 0.0, 14.5] + [(step - 36) * 0.5 for step in range(3, 73)]
    assert all(type(value) is float for value in columns["temperature_difference"])
    assert columns["case"] == [f"synthetic-{step:03d}" for step in range(73)]
    for number in range(1, 8):
        assert columns[f"sample_{number}"] == [step * (number + 1) for step in range(73)]
        assert all(type(value) is int for value in columns[f"sample_{number}"])
    assert returned["units"]["temperature_difference"] == "K" and returned["units"]["step"] == "unspecified"
    with (directory / "synthetic.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 73 and float(rows[64]["temperature_difference"]) == columns["temperature_difference"][64]


@pytest.mark.parametrize("kind", ["empty_directory", "populated_directory", "file", "dangling_symlink"])
def test_existing_destination_is_never_used_or_overwritten(tmp_path, kind):
    destination = tmp_path / "occupied"
    if kind == "file":
        destination.write_bytes(b"keep file")
    elif kind == "dangling_symlink":
        try:
            destination.symlink_to(tmp_path / "absent_target", target_is_directory=True)
        except OSError:
            pytest.skip("This Windows account cannot create symbolic links")
    else:
        destination.mkdir()
        if kind == "populated_directory":
            (destination / "important.txt").write_bytes(b"keep content")
    calls = []
    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("An existing destination must be rejected before creating a project")
    api = SimpleNamespace(operations=lambda: {"operations": sorted(offline.REQUIRED_OPERATIONS)},
                          projects=SimpleNamespace(create=forbidden))
    with pytest.raises(FileExistsError):
        offline.create_demo(api, destination)
    assert not calls
    if kind == "file":
        assert destination.read_bytes() == b"keep file"
    elif kind == "dangling_symlink":
        assert destination.is_symlink() and not (tmp_path / "absent_target").exists()
    elif kind == "populated_directory":
        assert list(destination.iterdir()) == [destination / "important.txt"]
        assert (destination / "important.txt").read_bytes() == b"keep content"
    else:
        assert list(destination.iterdir()) == []


@pytest.mark.parametrize("wait", [True, -1, 301, float("nan"), float("inf"), "1", None])
def test_invalid_observation_limit_has_no_filesystem_or_api_effect(tmp_path, wait):
    destination = tmp_path / "new"
    with pytest.raises(ValueError, match="wait_seconds"):
        offline.create_demo(SimpleNamespace(), destination, wait_seconds=wait)
    assert not destination.exists()


def test_older_bridge_is_rejected_before_creating_any_directory(tmp_path):
    destination = tmp_path / "new"
    api = SimpleNamespace(operations=lambda: {"operations": ["project.create"]})
    with pytest.raises(RuntimeError, match="missing operations"):
        offline.create_demo(api, destination)
    assert not destination.exists()


def test_observation_timeout_never_retries_cancels_or_recovers(monkeypatch):
    now, reads = [0.0], []
    monkeypatch.setattr(offline.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(offline.time, "sleep", lambda delay: now.__setitem__(0, now[0] + delay))
    original = {"id": "run", "status": "running"}
    def get(identity):
        reads.append(identity)
        return dict(original)
    # The narrow fake deliberately has no start/cancel/recover members.
    runs = SimpleNamespace(get=get)
    last, timed_out = offline._observe(runs, original, 0.25)
    assert timed_out and last == original and now[0] == 0.25
    assert reads == ["run", "run", "run"]
    reads.clear()
    assert offline._observe(runs, original, 0) == (original, True)
    assert reads == []
    done = {"id": "run", "status": "succeeded"}
    assert offline._observe(runs, done, 1) == (done, False)
    assert reads == []
