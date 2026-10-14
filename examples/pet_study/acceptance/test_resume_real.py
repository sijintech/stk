"""Explicit recovery of an owned public acceptance, without repeating MD stages.

The previous loopback Runtime must be stopped. Recreate it from known test
paths and sanitized profile metadata; never read its stored credentials/config.
"""
import os
from pathlib import Path
import sys
import threading
import time
from urllib.parse import urlparse

import pytest

from suan.runtime.client import RuntimeClient
from suan.runtime.server import RuntimeHTTPServer
from suan.runtime.supervisor import Supervisor
from suan.scripting import API
from suan.workflows.lammps import TABLE_ID as LAMMPS_TABLE_ID
from suan.workflows.pet_study import TABLE_ID
from test_study_real import verify_completed_study
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


TERMINAL = {"succeeded", "failed", "cancelled", "unknown"}


def frozen_task_ids(api, project, study_id, project_id):
    """Only accepted tasks reached through this study's canonical frozen children.

    The study service validates child IDs and metadata. The public simulation-run
    DTO supplies the accepted Runtime ID; a journal's task_id alone is insufficient.
    This function reads local journals and plans, never Runtime tasks or credentials.
    """
    study = api.lammps.get_pet_study(study_id, project=project)
    if study["project_id"] != project_id or study["study_id"] != study_id:
        raise ValueError("Acceptance cleanup belongs to a different project or study")
    allowed = {"relax", "property:modulus", "property:diffusion",
               *(f"property:tg:{index}" for index in range(len(study["recipe"]["tg"]["temperatures"])))}
    result = set()
    for key in allowed & study["stages"].keys():
        stage = study["stages"][key]
        owner = study["objects"][key]
        if stage["run_id"] != owner["run_id"]:
            raise ValueError("Acceptance cleanup child identity differs from its frozen study")
        for task in stage["tasks"]:
            if task["row"] != owner["record_id"] or task["step"] != "execute":
                raise ValueError("Acceptance cleanup task differs from its canonical child row")
            for reference in (task.get("progress"), task.get("produced")):
                if not reference or not reference.get("simulation_run_id"):
                    continue
                run = project.runs.get(reference["simulation_run_id"])
                plan = run["plan"]
                if (run["id"] != reference["simulation_run_id"] or plan["id"] != run["id"]
                        or plan["project_id"] != project_id
                        or plan["parameters"]["table_id"] != LAMMPS_TABLE_ID
                        or plan["parameters"]["record_id"] != owner["record_id"]
                        or plan["connection"] != study["simulation"]["connection"]
                        or plan["connection_identity"] != study["simulation"]["connection_identity"]):
                    raise ValueError("Acceptance cleanup simulation belongs to a different frozen child or Runtime")
                accepted = (run["status"].get("task") or {}).get("id")
                if reference.get("task_id") and reference["task_id"] != accepted:
                    raise ValueError("Acceptance cleanup task ID differs from its accepted simulation")
                if accepted:
                    if type(accepted) is not str:
                        raise ValueError("Invalid accepted Runtime task ID")
                    result.add(accepted)
    return result


def cancel_owned_tasks(client, supervisor, task_ids, *, timeout=8):
    """Cancel and reconcile only already verified IDs; never list or dispatch tasks."""
    pending = set()
    for identity in sorted(task_ids):
        record = client.task(identity)
        if record["id"] != identity:
            raise ValueError("Acceptance cleanup Runtime task identity changed")
        if record["state"] not in TERMINAL:
            client.cancel(identity)
            pending.add(identity)
    deadline = time.monotonic() + timeout
    while pending:
        for identity in tuple(pending):
            record = client.task(identity)
            if record["id"] != identity:
                raise ValueError("Acceptance cleanup Runtime task identity changed")
            if record["state"] not in TERMINAL:
                # refresh monitors this record without tick's global queue dispatch.
                supervisor.refresh(record)
                record = client.task(identity)
                if record["id"] != identity:
                    raise ValueError("Acceptance cleanup Runtime task identity changed")
            if record["state"] in TERMINAL:
                pending.remove(identity)
        if not pending or time.monotonic() >= deadline:
            break
        time.sleep(.1)
    if pending:
        print("PET acceptance cleanup still has owned active tasks:", sorted(pending), flush=True)


@pytest.mark.server
def test_resume_owned_real_acceptance(inproc, tmp_path, monkeypatch):
    project_path = Path(os.environ["STK_PET_STUDY_PROJECT"]).resolve(strict=True)
    root = project_path.parent
    assert project_path.name == "project" and (root / "state").is_dir() and (root / "shared").is_dir()
    monkeypatch.setenv("STK_PROFILES_FILE", str(root / "profiles" / "connections.json"))
    h = inproc()
    profiles = h.call("connections.list", {})["connections"]
    profile = next(value for value in profiles if value["id"] == "runtime:rt")
    target = urlparse(profile["url"])
    assert target.scheme == "http" and target.hostname == "127.0.0.1" and target.port
    # Public, low-entropy test placeholder only. Do not load existing config.json
    # or retrieve a credential from the connection store.
    token = "abcdefghijklmnopqrstu"
    config = {"state_dir": str(root / "state"), "workspace_root": str(root / "shared"),
              "port": target.port, "concurrency": 1, "poll_interval": 1., "scheduler_interval": 0,
              "token": token, "python": sys.executable}
    server = RuntimeHTTPServer(config)
    http = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
    http.start()
    supervisor = Supervisor(config)
    client = RuntimeClient(profile["url"], token)
    api, identity, project_id, owned_tasks = None, None, None, set()
    try:
        h.call("connections.add_runtime", {"name": "rt", "url": profile["url"], "token": token, "check": False})
        api = API(h.call)
        project = api.projects.open(project_path)
        api._project_handle = project.handle
        table = next(value for value in project.snapshot()["tables"] if value["id"] == TABLE_ID)
        assert len(table["records"]) == 1
        identity = table["records"][0]["id"]
        study = api.lammps.get_pet_study(identity)
        project_id = study["project_id"]
        owned_tasks.update(frozen_task_ids(api, project, identity, project_id))
        previous = {key: value["run_id"] for key, value in study["objects"].items() if "run_id" in value}
        before_tasks = {value["id"] for value in client.tasks()}
        api.lammps.recover_pet_study(identity, expected_revision=project.snapshot()["project"]["revision"])
        assert before_tasks == {value["id"] for value in client.tasks()}
        api.lammps.start_pet_study(identity, expected_revision=project.snapshot()["project"]["revision"])
        timeout = int(os.environ.get("STK_PET_ACCEPTANCE_TIMEOUT", "7200"))
        deadline, last = time.monotonic() + timeout, None
        while time.monotonic() < deadline:
            supervisor.tick()
            anchor = project.workflow_runs.get(study["run_id"])
            if anchor["status"] == "stopped" and not h.bridge.workflow_executor.active(
                    h.bridge.projects._stores[project.handle], study["run_id"]):
                break
            status = api.lammps.get_pet_study(identity)
            owned_tasks.update(frozen_task_ids(api, project, identity, project_id))
            summary = [(key, value["status"]) for key, value in status["stages"].items()]
            if summary != last:
                print("Recovered PET stages:", summary, flush=True)
                last = summary
            time.sleep(.2)
        else:
            pytest.fail("Recovered PET acceptance exceeded its explicit wait budget")
        status = api.lammps.get_pet_study(identity)
        owned_tasks.update(frozen_task_ids(api, project, identity, project_id))
        assert all(status["objects"][key]["run_id"] == value for key, value in previous.items())
        print("Recovered PET preserved child IDs:", sorted(previous), flush=True)
        verify_completed_study(api, project, h, (client, supervisor), study, anchor, tmp_path, monkeypatch)
    finally:
        try:
            if api is not None and identity is not None and project_id is not None:
                try:
                    # Verification may have moved/reopened the same project. Use
                    # its current handle and retain previously verified IDs if it closed.
                    owned_tasks.update(frozen_task_ids(api, api.project, identity, project_id))
                except Exception as error:
                    print("PET cleanup uses previously verified IDs; local source unavailable:",
                          type(error).__name__, flush=True)
            cancel_owned_tasks(client, supervisor, owned_tasks)
        finally:
            server.shutdown()
            server.server_close()
            http.join(5)


def test_offline_project_directory_uses_the_current_handle():
    from types import SimpleNamespace
    from test_study_real import project_directory
    values = [{"handle": "other", "directory": "/public/other"},
              {"handle": "current", "directory": "/public/current"}]
    api = SimpleNamespace(projects=SimpleNamespace(list=lambda: values))
    project = SimpleNamespace(handle="current")
    assert project_directory(api, project) == Path("/public/current")
    values.pop()
    with pytest.raises(ValueError, match="uniquely open"):
        project_directory(api, project)


def test_offline_cleanup_ids_require_matching_canonical_child_and_frozen_simulation():
    from types import SimpleNamespace
    owner = {"record_id": "row-owned", "run_id": "workflow-owned"}
    reference = {"simulation_run_id": "simulation-owned", "task_id": "task-owned"}
    study = {"project_id": "project-owned", "study_id": "study-owned",
        "recipe": {"tg": {"temperatures": [600]}},
        "simulation": {"connection": "runtime:rt", "connection_identity": "0000000000000000"},
        "objects": {"relax": owner},
        "stages": {"relax": {"run_id": "workflow-owned", "tasks": [
            {"row": "row-owned", "step": "execute", "progress": reference, "produced": None}]},
            "analysis:diffusion": {"tasks": [{"progress": {"task_id": "task-unrelated"}}]}}}
    simulation = {"id": "simulation-owned", "plan": {"id": "simulation-owned", "project_id": "project-owned",
        "parameters": {"table_id": LAMMPS_TABLE_ID, "record_id": "row-owned"},
        "connection": "runtime:rt", "connection_identity": "0000000000000000"},
        "status": {"task": {"id": "task-owned"}}}

    def get_run(identity):
        assert identity == "simulation-owned"
        return simulation

    project = SimpleNamespace(runs=SimpleNamespace(get=get_run))
    api = SimpleNamespace(lammps=SimpleNamespace(get_pet_study=lambda identity, **kwargs: study))
    assert frozen_task_ids(api, project, "study-owned", "project-owned") == {"task-owned"}
    for path, changed in ((simulation["plan"]["parameters"], "record_id"),
                          (simulation["plan"], "connection_identity"), (reference, "task_id")):
        original = path[changed]
        path[changed] = "unrelated"
        with pytest.raises(ValueError, match="different|differs"):
            frozen_task_ids(api, project, "study-owned", "project-owned")
        path[changed] = original
    with pytest.raises(ValueError, match="different project"):
        frozen_task_ids(api, project, "study-owned", "another-project")


def test_offline_cleanup_never_lists_cancels_or_dispatches_unrelated_tasks():
    from types import SimpleNamespace
    states = {"owned-running": "running", "owned-done": "succeeded", "unrelated": "running"}
    fetched, cancelled, refreshed = [], [], []

    def get_task(identity):
        fetched.append(identity)
        return {"id": identity, "state": states[identity]}

    def cancel(identity):
        cancelled.append(identity)
        states[identity] = "cancel_requested"

    def refresh(record):
        refreshed.append(record["id"])
        states[record["id"]] = "cancelled"

    client = SimpleNamespace(task=get_task, cancel=cancel,
                             tasks=lambda: pytest.fail("cleanup must never enumerate other Runtime tasks"))
    supervisor = SimpleNamespace(refresh=refresh,
                                 tick=lambda: pytest.fail("cleanup must never dispatch the Runtime queue"))
    cancel_owned_tasks(client, supervisor, {"owned-running", "owned-done"})
    assert cancelled == refreshed == ["owned-running"]
    assert "unrelated" not in fetched and states["unrelated"] == "running"
