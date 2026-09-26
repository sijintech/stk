"""End to end: MuPRO jobs queued by the STK Runtime.

Two paths run the fake muFerro from mupro_fake.py: `suan mupro` to the Runtime, and a paired
hub client (the template-by-id submission of stk-desktop's hub backend) through control, node
agent and Runtime to a DAT frame view.
No real SDK, licence or MPI launcher is used.
"""

import json
import os
import shutil
import time
import uuid

from click.testing import CliRunner
import pytest

from mupro_fake import make_fake_mpiexec, make_fake_sdk, write_case
from suan.cli.main import cli
from suan.control.agent import NodeAgent, frame_metadata
from suan.control.templates import MUFERRO_EXAMPLE_TEMPLATE, load_templates
from suan.runtime.common import read_json
from conftest import finish

pytestmark = pytest.mark.server

# Anything that could reach a real SDK, licence or MPI launcher, and the scheduler markers.
NODE_ENV = ("STK_MUPRO_ENV_SCRIPTS", "MUPRO_SDK_PREFIX", "MUPROROOT", "STK_MUPRO_ALLOW_LOCAL_MPI", "SLURM_JOB_ID",
            "PBS_JOBID", "SRUN_CPUS_PER_TASK")
OWNER = "test-owner-credential-" + "x"*32
AUTH = {"Authorization": "Bearer " + OWNER}


@pytest.fixture
def node(tmp_path, monkeypatch):
    """The Runtime service environment that workers inherit (C11): a fake SDK in
    MUPRO_SDK_PREFIX, no MPI or scheduler variables, and a fake bin dir first on PATH."""
    for key in [*NODE_ENV, *(key for key in os.environ if key.startswith("I_MPI_"))]:
        monkeypatch.delenv(key, raising=False)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.defpath)
    sdk = make_fake_sdk(tmp_path / "sdk")
    monkeypatch.setenv("MUPRO_SDK_PREFIX", str(sdk))
    return sdk, bin_dir


def suan(client, config, *args):
    """Run `suan` as a client of the test Runtime; the service itself never sees these variables."""
    return CliRunner().invoke(cli, list(args), env={"STK_RUNTIME_URL": client.url,
                                                    "STK_RUNTIME_TOKEN": config["token"]})


def submitted(result):
    """The task record `suan mupro submit` prints after its stderr progress lines."""
    assert result.exit_code == 0, result.output
    return json.loads(result.output[result.output.index("{"):])


def report(client, task_id, folder):
    return json.loads(client.download(task_id, "stk-mupro.json", folder / "stk-mupro.json").read_text())


def test_cli_submits_mupro_case_through_local_runtime(runtime, node, tmp_path):
    client, supervisor, server, config = runtime
    write_case(tmp_path / "case16")
    workspace = client.create_workspace("muFerro case")["id"]
    args = ["mupro", "submit", "--workspace", workspace, "--input", str(tmp_path / "case16"), "--ranks", "1",
            "--key", "case16-retry"]
    task = submitted(suan(client, config, *args))
    assert finish(client, supervisor, task["id"], timeout=60)["state"] == "succeeded"
    result = report(client, task["id"], tmp_path / "download")
    assert (result["state"], result["verification"]["status"], result["case_dir"]) == ("succeeded", "passed", "case16")
    assert result["layout"] == {"ranks": 1, "threads_per_rank": 1, "launcher": "none"}
    assert result["command"] == [str(node[0] / "bin" / "muFerro")]
    environment = read_json(server.service.task_dir(task["id"]) / "environment.json")
    assert environment["threads"] == {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    assert environment["argv"][1:] == ["-m", "suan.mupro", "run", "--ranks", "1", "--threads-per-rank", "1",
                                       "--case-dir", "case16"]
    fake = json.loads(client.download(task["id"], "case16/fake-muferro.json", tmp_path / "fake.json").read_text())
    assert (fake["OMP_NUM_THREADS"], fake["MKL_NUM_THREADS"], fake["MUPROROOT"]) == ("1", "1", None)
    result = suan(client, config, "mupro", "result", task["id"])
    assert result.exit_code == 0, result.output
    # A retry after a lost response reuses the key and never queues a second run.
    assert submitted(suan(client, config, *args))["id"] == task["id"]
    assert len(client.tasks()) == 1


def test_local_multirank_via_runtime_is_refused_then_allowed(runtime, node, tmp_path, monkeypatch):
    client, supervisor, server, config = runtime
    sdk, bin_dir = node
    workspace = client.create_workspace("muFerro ranks")["id"]
    args = ["mupro", "submit", "--workspace", workspace, "--example", "--ranks", "2"]
    task = submitted(suan(client, config, *args))
    assert finish(client, supervisor, task["id"], timeout=60)["state"] == "failed"
    refused = report(client, task["id"], tmp_path / "refused")
    assert (refused["state"], refused["classification"], refused["command"]) == ("failed", "configuration", [])
    assert "0.0.0.0" in refused["reason"] and "STK_MUPRO_ALLOW_LOCAL_MPI=1" in refused["reason"]

    # The operator opts in through the Runtime service environment, never through the TaskSpec.
    mpiexec = make_fake_mpiexec(bin_dir)
    assert shutil.which("mpiexec") == str(mpiexec)
    monkeypatch.setenv("STK_MUPRO_ALLOW_LOCAL_MPI", "1")
    task = submitted(suan(client, config, *args))
    assert finish(client, supervisor, task["id"], timeout=60)["state"] == "succeeded"
    allowed = report(client, task["id"], tmp_path / "allowed")
    assert allowed["verification"]["status"] == "passed"
    assert allowed["layout"] == {"ranks": 2, "threads_per_rank": 1, "launcher": "mpiexec"}
    assert allowed["command"] == [str(mpiexec), "-n", "2", str(sdk / "bin" / "muFerro")]
    environment = read_json(server.service.task_dir(task["id"]) / "environment.json")
    assert environment["layout"] == {"nodes": 1, "ranks": 2, "threads_per_rank": 1}
    assert environment["threads"] == {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}


class Control:
    """A paired client device's requests, carried by the in-process control app."""

    def __init__(self, http, token):
        self.http, self.token = http, token

    def request(self, method, path, body=None):
        response = self.http.request(method, "/api/v1/" + path, json=body,
                                     headers={"Authorization": "Bearer " + self.token})
        if response.status_code >= 400:
            raise ValueError(response.json().get("detail", "Control request rejected"))
        return response.json()


def paired(http, role, profile=""):
    body = {"role": role, **({"profile": profile} if profile else {})}
    code = http.post("/api/v1/pairings", json=body, headers=AUTH).json()["code"]
    return http.post("/api/v1/pairings/claim", json={"code": code, "name": role}).json()


def command(kind, payload):
    return {"id": uuid.uuid4().hex, "kind": kind, "payload": payload}


def serve_node(http, ws, agent, action_id):
    """One node-agent round on the open node connection, as the real agent keeps one: run the
    dispatched action and wait until control records its result; returns the action record."""
    # Control dispatches only queued actions; any other state would block receive_json forever.
    assert http.get("/api/v1/actions/" + action_id, headers=AUTH).json()["state"] == "queued"
    action = ws.receive_json()["action"]
    assert action["id"] == action_id, action
    ws.send_json({"type": "result", "id": action["id"], "result": agent.execute(action)})
    deadline = time.monotonic() + 10
    while True:
        record = http.get("/api/v1/actions/" + action_id, headers=AUTH).json()
        if record["state"] == "succeeded":
            return record
        assert time.monotonic() < deadline, record
        time.sleep(.05)


def test_hub_template_runs_fake_muferro_and_views_frames(runtime, node, tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("vtk")
    from fastapi.testclient import TestClient
    from suan.control.app import create_app
    from suan.render.v1 import validate_scene
    client, supervisor, _, _ = runtime
    app = create_app(tmp_path / "control", OWNER, load_templates(["muferro-example"]))
    agent = NodeAgent(client, tmp_path / "agent")
    with TestClient(app) as http:
        node_device = paired(http, "node")
        desktop = Control(http, paired(http, "client", "desktop")["token"])
        with http.websocket_connect("/api/v1/nodes/connect",
                                    headers={"Authorization": "Bearer " + node_device["token"]}) as ws:

            def post(kind, payload):
                action = {**command(kind, payload), "node_id": node_device["device_id"]}
                desktop.request("POST", "actions", action)
                return action["id"]

            def step(kind, payload):
                """The client posts an action and the node agent runs it; returns the action's result."""
                return serve_node(http, ws, agent, post(kind, payload))["result"]

            workspace = step("workspace.create", {"name": "muFerro 示例"})["id"]
            # The payload of stk-desktop's hub backend for a template run (HubBackend.submit).
            submitted = post("task.submit", {"template": "muferro-example", "workspace_id": workspace})
            stored = http.get("/api/v1/actions/" + submitted, headers=AUTH).json()
            assert stored["state"] == "queued" and stored["review_reason"] == ""
            assert stored["request"]["payload"] == {"template": "muferro-example", "spec": {
                **MUFERRO_EXAMPLE_TEMPLATE, "workspace_id": workspace, "name": "muferro-example"}}
            task_id = serve_node(http, ws, agent, submitted)["result"]["id"]
            # Control drops a node that sends nothing for 30 s; the real agent sends snapshots.
            ws.send_json({"type": "snapshot", "snapshot": agent.snapshot()})
            assert finish(client, supervisor, task_id, timeout=25)["state"] == "succeeded"
            result = report(client, task_id, tmp_path / "download")
            assert result["verification"]["status"] == "passed"
            environment = read_json(supervisor.service.task_dir(task_id) / "environment.json")
            assert environment["threads"] == {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}

            artifacts = step("task.artifacts", {"task_id": task_id})
            frames = [a["path"] for a in artifacts if a["path"].startswith("Polar.")]
            assert frames == ["Polar.00000000.dat", "Polar.00000002.dat"]
            assert [frame_metadata(path)["timestep"] for path in frames] == [0, 2]
            assert [f["path"] for f in result["frames"] if f["stem"] == "Polar"] == frames

            scene = step("view.build", {"task_id": task_id, "path": frames[-1],
                                        "options": {"mode": "slice", "axis": 2, "index": 1, "component": "magnitude",
                                                    "level": 0.0}})
            manifest = validate_scene(scene)["manifest"]
            assert (manifest["field"], manifest["timestep"], manifest["coordinate_units"]) == ("Polar", 2, "grid index")
            assert (manifest["dimensions"], manifest["components"]) == ([4, 3, 2], 3)
            assert manifest["source"]["path"] == frames[-1]
            probe = step("view.probe", {"task_id": task_id, "path": frames[-1], "position": [2.0, 1.0, 1.0]})
            i, j, k = 3, 2, 2  # One-based indices of the probed grid point.
            assert probe["values"] == pytest.approx([i + 10*j + 100*k + 1000*c + 2 for c in (1, 2, 3)])


def test_policy_reviews_changed_mupro_template_request(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from suan.control.app import create_app
    workspace = "a"*32
    exact = {**MUFERRO_EXAMPLE_TEMPLATE, "workspace_id": workspace, "name": "muferro-example"}
    changed = {**exact, "backend": "slurm", "resources": {**exact["resources"], "queue": "cpu"}}
    with TestClient(create_app(tmp_path, OWNER, load_templates(["muferro-example"]))) as http:
        node_id = paired(http, "node")["device_id"]
        stored = []
        for spec in (exact, changed):
            action = {**command("task.submit", {"template": "muferro-example", "spec": spec}), "node_id": node_id}
            response = http.post("/api/v1/actions", json=action, headers=AUTH)
            assert response.status_code == 202, response.text
            stored.append(response.json())
    assert [action["state"] for action in stored] == ["queued", "review"]
    assert "模板变更" in stored[1]["review_reason"]
