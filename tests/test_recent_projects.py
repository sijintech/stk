"""Local history survives bridge sessions but never substitutes for explicit project opening."""
import json
from uuid import uuid4

from suan.project import ProjectStore
from suan.desktop_bridge.recent_projects import RecentProjects, LIMIT
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


def test_history_survives_restart_orders_by_open_and_forgets_without_deleting(inproc, tmp_path):
    harness = inproc()
    assert harness.call("project.recent") == {"projects": [], "warning": ""}
    a, b = tmp_path / "项目 A", tmp_path / "B"
    first = harness.call("project.create", {"directory": str(a), "name": "甲"})["project"]
    second = harness.call("project.create", {"directory": str(b), "name": "乙"})["project"]
    harness.call("project.open", {"directory": str(a)})
    recent = harness.call("project.recent")["projects"]
    assert [item["id"] for item in recent] == [first["id"], second["id"]]
    assert all("handle" not in item and item["last_opened"] for item in recent)
    harness.close()
    restarted = inproc()
    assert restarted.call("project.list")["projects"] == []
    assert restarted.call("project.recent")["projects"] == recent
    opened = restarted.call("project.open", {"directory": recent[0]["directory"], "expected_id": recent[0]["id"]})["project"]
    assert opened["handle"] != first["handle"]
    assert restarted.call("project.forget", {"directory": str(a)}) == {"removed": True}
    assert restarted.call("project.list")["projects"] == [opened]
    assert ProjectStore(a).info()["id"] == first["id"]
    assert restarted.call("project.forget", {"directory": str(a)}) == {"removed": False}
    assert [p["id"] for p in restarted.call("project.recent")["projects"]] == [second["id"]]
    assert not harness.violations and not restarted.violations


def test_missing_and_replaced_projects_leave_history_and_sessions_unchanged(inproc, tmp_path):
    directory = tmp_path / "old"
    harness = inproc()
    info = harness.call("project.create", {"directory": str(directory), "name": "Old"})["project"]
    harness.call("project.close", {"handle": info["handle"]})
    directory.rename(tmp_path / "moved")
    recent = harness.call("project.recent")["projects"]
    assert len(recent) == 1  # metadata only; missing directories are not silently pruned
    params = {"directory": str(directory), "expected_id": info["id"]}
    assert harness.error("project.open", params)["code"] == "not_found"
    ProjectStore.create(directory, "Replacement")
    assert harness.error("project.open", params)["code"] == "conflict"
    assert harness.call("project.list")["projects"] == []
    assert harness.call("project.recent")["projects"] == recent
    assert harness.error("project.open", {**params, "expected_id": "invalid"})["code"] == "invalid_params"
    assert harness.call("project.forget", {"directory": str(directory)})["removed"]


def test_corrupt_history_does_not_prevent_project_creation_or_overwrite_original(inproc, tmp_path):
    state = tmp_path / "bridge"
    state.mkdir()
    path = state / "recent-projects.json"
    path.write_bytes(b'{"version":999}')
    harness = inproc()
    info = harness.call("project.create", {"directory": str(tmp_path / "project"), "name": "A"})["project"]
    assert ProjectStore(tmp_path / "project").info()["id"] == info["id"]
    recent = harness.call("project.recent")
    assert recent["projects"] == [] and "history" in recent["warning"]
    assert harness.error("project.forget", {"directory": str(tmp_path / "project")})["code"] == "unavailable"
    assert path.read_bytes() == b'{"version":999}'


def test_failed_preference_write_keeps_previous_history_and_open_success(inproc, tmp_path, monkeypatch):
    import suan.desktop_bridge.recent_projects as module
    harness = inproc()
    a = harness.call("project.create", {"directory": str(tmp_path / "a"), "name": "A"})["project"]
    original = module.atomic_json
    def denied(*args):
        raise PermissionError("read-only preferences")
    monkeypatch.setattr(module, "atomic_json", denied)
    b = harness.call("project.create", {"directory": str(tmp_path / "b"), "name": "B"})["project"]
    result = harness.call("project.recent")
    assert [p["id"] for p in result["projects"]] == [a["id"]]
    assert "read-only" in result["warning"]
    assert harness.error("project.forget", {"directory": str(tmp_path / "a")})["code"] == "unavailable"
    assert len(harness.call("project.list")["projects"]) == 2
    monkeypatch.setattr(module, "atomic_json", original)
    harness.call("project.open", {"directory": b["directory"]})
    assert harness.call("project.recent")["warning"] == ""


def test_bounded_history_reloads_without_inspecting_project_paths(tmp_path, monkeypatch):
    history = RecentProjects(tmp_path)
    for index in range(LIMIT + 3):
        history.remember({"id": str(uuid4()), "name": str(index), "directory": str(tmp_path / str(index))})
    result = history.list()
    assert len(result["projects"]) == LIMIT and result["projects"][0]["name"] == str(LIMIT + 2)
    assert not (tmp_path / "0").exists()
    assert RecentProjects(tmp_path).list() == result
    saved = json.loads(history.path.read_text())
    assert saved["version"] == 1 and len(saved["projects"]) == LIMIT
