"""MuPRO through the control service: templates, template submission by id, the Linux-only server guard,
DAT frame identity and node-agent views (scene v1)."""
import json
import sys
import uuid

from click.testing import CliRunner
import pytest

from suan.control.agent import NodeAgent, frame_metadata
from suan.control.policy import DEMO_TEMPLATE, validate_action
from suan.control.templates import BUILTIN_TEMPLATES, MUFERRO_EXAMPLE_TEMPLATE, load_templates
from suan.mupro import muferro_spec
from suan.runtime.models import TaskSpec
from conftest import finish

WORKSPACE = "b"*32
NODE = "c"*32
CASE_TEMPLATE = {"argv": ["{python}", "-m", "suan.mupro", "run", "--case-dir", "case"],
                 "inputs": ["case/input.toml"], "outputs": ["stk-mupro.json"]}
# muFerro's energy_out.dat header and 'kt:' rows (apps/muFerro/src/output.f90 formats 5001 and 5004).
ENERGY_OUT = ("      step         " + "".join(f"{h:>18}" for h in (
    "Elastic Energy", "Electric Energy", "Landau Energy", "Gradient P Energy", "Total Energy")) + "\n"
    "kt:      0 energy:   0.1000000000E+01  0.2000000000E+01  0.3000000000E+01  0.4000000000E+01  0.1000000000E+02\n"
    "kt:      1 energy:   0.1000000000E+01  0.2000000000E+01  0.3000000000E+01  0.3000000000E+01  0.9000000000E+01\n")
# Header-first muFerro frames: 'nx ny nz ncomp' with one-based 'i j k c v' rows, and 'nx ny nz' with 'i j k v'.
FRAMES = r'''
from pathlib import Path
import sys
Path("energy_out.dat").write_text(sys.argv[1])
rows = [f"{4:5d}{3:5d}{2:5d}{3:5d}"]
rows += [f"{i:5d}{j:5d}{k:5d}{c:5d}{i + 10*j + 100*k + 1000*c + 100:22.12E}"
         for k in (1, 2) for j in (1, 2, 3) for i in (1, 2, 3, 4) for c in (1, 2, 3)]
Path("Polar.00000100.dat").write_text("\n".join(rows) + "\n")
rows = [f"{4:5d}{3:5d}{2:5d}"]
rows += [f"{i:5d}{j:5d}{k:5d}{-(i + 10*j + 100*k):22.12E}" for k in (1, 2) for j in (1, 2, 3) for i in (1, 2, 3, 4)]
Path("Elec_Phi.00000101.dat").write_text("\n".join(rows) + "\n")
'''


def test_builtin_and_file_templates_load_and_validate(tmp_path):
    templates = load_templates(["muferro-example", "demo-field", "muferro-example"])
    assert templates == BUILTIN_TEMPLATES and templates is not BUILTIN_TEMPLATES
    templates["muferro-example"]["argv"].append("--changed")
    assert MUFERRO_EXAMPLE_TEMPLATE["argv"][-1] == "--example"
    spec = TaskSpec(**MUFERRO_EXAMPLE_TEMPLATE, workspace_id=WORKSPACE, name="muferro-example")
    assert spec.inputs == [] and spec.outputs == ["stk-mupro.json"] and spec.env == {}
    # The CLI's example submission, so the worker records and pins the same MPI thread settings.
    built = muferro_spec(WORKSPACE, example=True, walltime_seconds=600, memory_mb=4096, name="muferro-example")
    assert TaskSpec(**built) == spec
    # The control service expands a template-only payload this way; it must stay auto-approved.
    request = {"id": "d"*32, "node_id": NODE, "kind": "task.submit", "payload": {
        "template": "muferro-example", "spec": {**MUFERRO_EXAMPLE_TEMPLATE, "workspace_id": WORKSPACE, "name": "muferro-example"}}}
    assert validate_action(request, BUILTIN_TEMPLATES) == ""
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"muferro-case": CASE_TEMPLATE, "demo.v2_x": DEMO_TEMPLATE}))
    assert load_templates(["muferro-example"], [good]) == {
        "muferro-example": MUFERRO_EXAMPLE_TEMPLATE, "muferro-case": CASE_TEMPLATE, "demo.v2_x": DEMO_TEMPLATE}
    with pytest.raises(ValueError, match="Unknown built-in"):
        load_templates(["arbitrary"])
    for content, message in [
        ({"with-env": {**CASE_TEMPLATE, "env": {"OMP_NUM_THREADS": "8"}}}, "must not set env"),
        ({"Bad ID": CASE_TEMPLATE}, "template ID"),
        ({"-leading": CASE_TEMPLATE}, "template ID"),
        ({"x"*65: CASE_TEMPLATE}, "template ID"),
        ({"no-argv": {"outputs": ["a.dat"]}}, "must be an object with argv"),
        ({"extra": {**CASE_TEMPLATE, "name": "other"}}, "allows only"),
        ({"muferro-example": CASE_TEMPLATE}, "Duplicate"),
        ({"empty-argv": {"argv": []}}, "Invalid template empty-argv"),
        ({"escape": {**CASE_TEMPLATE, "outputs": ["../stk-mupro.json"]}}, "Invalid template escape"),
        ({"bad-backend": {**CASE_TEMPLATE, "backend": ["slurm"]}}, "Invalid template bad-backend"),
        ({"unbounded": {**CASE_TEMPLATE, "backend": "slurm"}}, "must set resources.walltime_seconds"),
        ([CASE_TEMPLATE], "JSON object"),
    ]:
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps(content))
        with pytest.raises(ValueError, match=message):
            load_templates(["muferro-example"], [bad])
    with pytest.raises(ValueError, match="Duplicate"):
        load_templates([], [good, good])
    case = json.dumps(CASE_TEMPLATE)
    for text in [f'{{"muferro-case": {case}, "muferro-case": {case}}}',
                 '{"repeated-argv": {"argv": ["true"], "argv": ["false"]}}']:
        bad.write_text(text)
        with pytest.raises(ValueError, match="Duplicate key in template file"):
            load_templates([], [bad])


def test_frame_metadata_from_artifact_path():
    assert frame_metadata("Polar.00000100.dat") == {"field": "Polar", "timestep": 100}
    assert frame_metadata("case16/Elec_Phi.00000101.dat") == {"field": "Elec_Phi", "timestep": 101}
    for path in ["energy_out.dat", "Polarization.00000001.dat", "Polar.1.dat", "Polar.00000100.vti"]:
        assert frame_metadata(path) is None


def test_read_field_rejects_time_series_table(tmp_path):
    pytest.importorskip("numpy")
    from toolkits.sviz.field import read_field
    table = tmp_path / "energy_out.dat"
    table.write_text(ENERGY_OUT)
    with pytest.raises(ValueError, match="Not a regular-grid field DAT"):
        read_field(table)
    table.write_text(ENERGY_OUT.split("\n", 1)[1])
    with pytest.raises(ValueError, match="Not a regular-grid field DAT"):
        read_field(table)
    # MuPRO's library writer (L1_IO/io.f90:136) ends the header with a Fortran comment.
    frame = tmp_path / "Grain.00000100.dat"
    frame.write_text("4 3 2 ! comment: nx ny nz\n" + "".join(
        f"{i} {j} {k} {i + 10*j + 100*k}.0\n" for i in (1, 2, 3, 4) for j in (1, 2, 3) for k in (1, 2)))
    data = read_field(frame)
    assert data.shape == (4, 3, 2, 1) and data[3, 2, 1, 0] == 4 + 30 + 200


class Hub:
    """Stands in for the HubClient that HubBackend.submit posts to; every action finishes at once."""

    url = "http://127.0.0.1:8790"

    def __init__(self):
        self.posts = []

    def post_action(self, body):
        self.posts.append(body)
        return {"id": body["id"], "node_id": body["node_id"], "state": "succeeded", "request": body,
                "result": {"id": "t"*32, "workspace_id": WORKSPACE}}


def test_desktop_submits_hub_template_by_id():
    from suan.desktop_bridge.backends import HubBackend, action_id
    from suan.desktop_bridge.protocol import BridgeError
    hub = Hub()
    backend = HubBackend("hub:lab", hub, NODE)
    out = backend.submit(None, "run-1", template="muferro-example", workspace_id=WORKSPACE)
    assert out["action"]["state"] == "succeeded" and out["task"]["id"] == "t"*32
    # A template-only payload: the control service expands it into the registered spec (policy check above).
    assert hub.posts == [{"id": action_id("task.submit", NODE, "run-1"), "node_id": NODE, "kind": "task.submit",
                          "payload": {"template": "muferro-example", "workspace_id": WORKSPACE}}]
    # The same idempotency key is the same hub action, so a retry never queues a second run.
    backend.submit(None, "run-1", template="muferro-example", workspace_id=WORKSPACE)
    assert hub.posts[1]["id"] == hub.posts[0]["id"]
    with pytest.raises(BridgeError, match="workspace_id"):
        backend.submit(None, "run-2", template="muferro-example")


@pytest.mark.server
def test_control_serve_registers_templates(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("uvicorn")
    from fastapi.testclient import TestClient
    from suan.control.cli import control
    served = []
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: served.append((app, kwargs)))
    for name in ("STK_MODEL_URL", "STK_MODEL_NAME", "STK_MODEL_KEY"):
        monkeypatch.delenv(name, raising=False)
    state = tmp_path / "control"
    runner = CliRunner()
    assert runner.invoke(control, ["init", "--state-dir", str(state)]).exit_code == 0
    extra = tmp_path / "templates.json"
    extra.write_text(json.dumps({"muferro-case": CASE_TEMPLATE}))
    result = runner.invoke(control, ["serve", "--state-dir", str(state), "--template", "muferro-example",
                                     "--template-file", str(extra)])
    assert result.exit_code == 0, result.output
    owner = json.loads((state / "control.json").read_text())["owner_token"]

    def listed():
        app, options = served.pop()
        assert options["host"] == "127.0.0.1"
        with TestClient(app) as http:
            return http.get("/api/v1/templates", headers={"Authorization": "Bearer " + owner}).json()

    assert listed() == {"muferro-example": MUFERRO_EXAMPLE_TEMPLATE, "muferro-case": CASE_TEMPLATE}
    result = runner.invoke(control, ["serve", "--state-dir", str(state), "--allow-demo-template"])
    assert result.exit_code == 0, result.output
    assert listed() == {"demo-field": DEMO_TEMPLATE}
    result = runner.invoke(control, ["serve", "--state-dir", str(state), "--allow-demo-template", "--template", "demo-field"])
    assert result.exit_code == 0, result.output
    assert listed() == {"demo-field": DEMO_TEMPLATE}
    assert runner.invoke(control, ["serve", "--state-dir", str(state), "--template", "arbitrary"]).exit_code != 0
    extra.write_text(json.dumps({"muferro-example": CASE_TEMPLATE}))
    result = runner.invoke(control, ["serve", "--state-dir", str(state), "--template", "muferro-example",
                                     "--template-file", str(extra)])
    assert result.exit_code == 1 and "Duplicate template ID" in result.output
    assert served == []


def test_control_and_node_services_refuse_off_linux(tmp_path, monkeypatch):
    from suan.control.cli import control, node
    monkeypatch.setattr(sys, "platform", "win32")
    runtime_state, paired = tmp_path / "runtime", tmp_path / "paired"
    runtime_state.mkdir()
    paired.mkdir()
    state = tmp_path / "control"
    runner = CliRunner()
    for group, args in [
        # serve first: without control.json it could never reach uvicorn.run.
        (control, ["serve", "--state-dir", str(state), "--template", "muferro-example"]),
        (control, ["init", "--state-dir", str(state)]),
        (control, ["pair", "--state-dir", str(paired), "--role", "node"]),
        (node, ["pair", "--control-url", "http://127.0.0.1:9", "--code", "one-time-code", "--name", "n",
                "--runtime-state-dir", str(runtime_state), "--state-dir", str(state)]),
        (node, ["run", "--state-dir", str(paired)]),
    ]:
        result = runner.invoke(group, args)
        assert result.exit_code == 1, (args, result.output)
        # Other computers are hub clients: stk-desktop paired with a desktop-profile code through a
        # tunnel, not a suan CLI connection profile (suan connect ... --profile NAME).
        assert "Linux only" in result.output and "stk-desktop" in result.output
        assert "--profile desktop" in result.output and "suan connect" not in result.output
    assert not state.exists()
    assert list(runtime_state.iterdir()) == list(paired.iterdir()) == []
    assert runner.invoke(control, ["init", "--help"]).exit_code == 0


def test_agent_views_mupro_frames_with_step_identity(runtime, tmp_path):
    pytest.importorskip("vtk")
    from suan.render.v1 import validate_scene
    client, supervisor, _, _ = runtime
    workspace = client.create_workspace("MuPRO frames")
    task = client.submit({"workspace_id": workspace["id"], "argv": [sys.executable, "-c", FRAMES, ENERGY_OUT],
                          "outputs": ["Polar.00000100.dat", "Elec_Phi.00000101.dat", "energy_out.dat"]})
    assert finish(client, supervisor, task["id"])["state"] == "succeeded"
    assert [a["path"] for a in client.artifacts(task["id"])] == [
        "Elec_Phi.00000101.dat", "Polar.00000100.dat", "energy_out.dat"]
    agent = NodeAgent(client, tmp_path / "agent")

    def run(kind, path, **payload):
        return agent.execute({"id": uuid.uuid4().hex, "node_id": NODE, "kind": kind,
                              "payload": {"task_id": task["id"], "path": path, **payload}})

    # The option shapes of a view.build request (as the web viewer sends them), level included.
    slice_view = run("view.build", "Polar.00000100.dat",
                     options={"mode": "slice", "axis": 2, "index": 1, "component": "magnitude", "level": 0.0})
    manifest = validate_scene(slice_view)["manifest"]
    assert (manifest["field"], manifest["timestep"]) == ("Polar", 100)
    assert (manifest["coordinate_units"], manifest["units"]) == ("grid index", "unspecified")
    assert (manifest["dimensions"], manifest["components"]) == ([4, 3, 2], 3)
    assert manifest["source"] == {"task_id": task["id"], "path": "Polar.00000100.dat"}
    level = sum(manifest["value_range"]) / 2
    iso = run("view.build", "Polar.00000100.dat",
              options={"mode": "iso", "axis": 2, "index": 1, "component": "magnitude", "level": level})
    assert validate_scene(iso)["mesh"]["indices"] and iso["manifest"]["timestep"] == 100
    vectors = run("view.build", "Polar.00000100.dat",
                  options={"mode": "vectors", "axis": 2, "index": 1, "component": "magnitude", "level": 0.0})
    assert validate_scene(vectors)["mesh"]["indices"] and vectors["manifest"]["field"] == "Polar"
    probe = run("view.probe", "Polar.00000100.dat", position=[2.0, 1.0, 1.0])
    i, j, k = 3, 2, 2
    assert probe["values"] == [i + 10*j + 100*k + 1000*c + 100 for c in (1, 2, 3)]
    scalar = run("view.build", "Elec_Phi.00000101.dat",
                 options={"mode": "slice", "axis": 0, "index": 0, "component": 0, "level": 0.0})
    assert (scalar["manifest"]["field"], scalar["manifest"]["timestep"], scalar["manifest"]["components"]) == (
        "Elec_Phi", 101, 1)
    with pytest.raises(ValueError, match="time step"):
        run("view.build", "Polar.00000100.dat", options={"timestep": 0})
    with pytest.raises(ValueError, match="Not a regular-grid field DAT"):
        run("view.build", "energy_out.dat", options={"mode": "slice"})
    named = run("view.build", "Polar.00000100.dat", metadata={"field": "P"}, options={"mode": "slice"})
    assert (named["manifest"]["field"], named["manifest"]["timestep"]) == ("P", 100)
    scaled = run("view.build", "Polar.00000100.dat", metadata={"spacing": [.5, .5, .5]}, options={"mode": "slice"})
    assert scaled["manifest"]["coordinate_units"] == "unspecified" and scaled["manifest"]["timestep"] == 100
    with pytest.raises(ValueError, match="Unknown scientific metadata"):
        run("view.build", "Polar.00000100.dat", metadata={"timestep": 7})
