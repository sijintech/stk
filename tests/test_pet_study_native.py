"""Fixed native PET dispatch, with real project revisions and prepared journals."""
import json

import pytest

from suan.workflows.pet_study_native import native_action
from test_pet_study import study  # noqa: F401
from test_workflow_native import project_api  # noqa: F401
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


@pytest.mark.parametrize("action,params", [
    ("__dict__", {}), ([], {}), ("create", []), ("create", {"connection": "unused"}),
    ("get", {"project_id": "invalid", "expected_revision": 0, "study_id": "unused"}),
    ("get", {"project_id": "9e571686-b05d-51f5-b243-be046b33ae40", "expected_revision": True, "study_id": "unused"}),
    ("start", {"project_id": "9e571686-b05d-51f5-b243-be046b33ae40", "expected_revision": 0,
               "study_id": "unused", "project": "override"}),
])
def test_bad_dispatch_rejected_before_project_access(action, params):
    with pytest.raises(ValueError):
        native_action(object(), action, params)


def test_stale_or_switched_project_rejected_before_study_access(project_api):
    s = project_api
    identity = s["p"].snapshot()["project"]["id"]
    with pytest.raises(ValueError, match="project changed"):
        native_action(s["api"], "create", {"project_id": identity, "expected_revision": 1, "connection": "unused"})
    other = s["api"].projects.create(s["tmp"] / "other", "Other")
    s["api"]._project_handle = other.handle
    with pytest.raises(ValueError, match="project changed"):
        native_action(s["api"], "start", {"project_id": identity, "expected_revision": 0, "study_id": "unused"})
    assert s["p"].snapshot()["project"]["revision"] == other.snapshot()["project"]["revision"] == 0


def test_native_create_freezes_without_execution_and_status_is_bounded(study, capsys):
    s = study
    params = {"project_id": s["p"].snapshot()["project"]["id"], "expected_revision": 0,
              "connection": s["connection"], "options": s["options"], "recipe": s["recipe"], "wait_seconds": 300,
              "study_id": "e334598c-edf4-4760-af3f-401603bb4249"}
    made = native_action(s["api"], "create", params)
    assert made["status"] == "prepared" and made["wait_seconds"] == 300
    assert made["study_id"] == params["study_id"]
    assert s["calls"] == [] and s["runtime"][0].tasks() == []
    before = s["p"].snapshot()["project"]["revision"]
    viewed = native_action(s["api"], "get", {"project_id": made["project_id"], "expected_revision": before,
                                            "study_id": made["study_id"]})
    assert viewed["run_id"] == made["run_id"] and s["p"].snapshot()["project"]["revision"] == before
    for line in capsys.readouterr().out.splitlines():
        if line.startswith("PET study: "):
            summary = json.loads(line.removeprefix("PET study: "))
            assert set(summary) == {"study_id", "run_id", "status", "complete", "definition_changed", "stages"}
    assert s["calls"] == [] and s["runtime"][0].tasks() == []
