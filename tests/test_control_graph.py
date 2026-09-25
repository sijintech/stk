"""graph.evaluate / graph.meta / task.events through the hub: policy, agent lanes, blobs, end to end."""
import asyncio
import copy
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid

import pytest

from suan.control.policy import GRAPH_REVIEW, validate_action

AGENT_FEATURES = ["graph.evaluate", "graph.meta", "task.events", "graph.cancel", "read", "workspace.files",
                  "workspace.import"]

OWNER = "test-owner-credential-" + "x" * 32
AUTH = {"Authorization": "Bearer " + OWNER}
TASK = "d" * 32
NODE = "c" * 32
NODE_ENV = ("STK_MUPRO_ENV_SCRIPTS", "MUPRO_SDK_PREFIX", "MUPROROOT", "STK_MUPRO_ALLOW_LOCAL_MPI", "SLURM_JOB_ID",
            "PBS_JOBID", "SRUN_CPUS_PER_TASK")


def muferro_graph():
    """Sources + render + view + output + plot nodes only (all present in the base catalog)."""
    return {
        "schema": "stk.graph/1", "catalog": {"stk": 1},
        "parameters": [{"name": "step", "type": "step", "default": "latest"},
                       {"name": "view", "type": "enum", "choices": ["iso", "+x", "-x"], "default": "iso"}],
        "nodes": [
            {"id": "run", "type": "stk.source.muferro_run@1", "params": {"binding": "run"}},
            {"id": "polar", "type": "stk.source.muferro_frame@1", "inputs": {"frames": {"from": "run.frames"}},
             "params": {"dataset": "Polar", "step": {"$param": "step"}}},
            {"id": "volume", "type": "stk.render.volume@1", "inputs": {"in": {"from": "polar.out"}}},
            {"id": "bar", "type": "stk.render.scalar_bar@1", "inputs": {"source": {"from": "volume.layer"}}},
            {"id": "box", "type": "stk.render.outline@1", "inputs": {"in": {"from": "polar.out"}}},
            {"id": "axes", "type": "stk.render.axes@1"},
            {"id": "camera", "type": "stk.view.camera@1", "params": {"preset": {"$param": "view"}}},
            {"id": "scene", "type": "stk.view.scene@1",
             "inputs": {"layers": [{"from": "volume.layer"}, {"from": "bar.layer"}, {"from": "box.layer"},
                                   {"from": "axes.layer"}], "camera": {"from": "camera.camera"}}},
            {"id": "payload", "type": "stk.output.payload@1", "inputs": {"scene": {"from": "scene.scene"}}},
            {"id": "energy_plot", "type": "stk.plot.line@1", "inputs": {"table": {"from": "run.energy"}},
             "params": {"x": "step", "y": ["Total Energy"], "y_label": "Energy (normalized)"}},
            {"id": "energy_png", "type": "stk.output.image@1", "inputs": {"source": {"from": "energy_plot.plot"}},
             "params": {"width": 320, "height": 240}},
        ],
        "outputs": {"payload": "payload.payload", "energy_plot": "energy_plot.plot", "energy_png": "energy_png.image",
                    "energy": "run.energy"},
    }


def evaluate_action(payload, node_id=NODE):
    return {"id": uuid.uuid4().hex, "node_id": node_id, "kind": "graph.evaluate", "payload": payload}


def policy(payload):
    return validate_action(evaluate_action(payload), {})


# ---------------------------------------------------------------------------
# Policy (no fastapi, no NumPy)


def test_graph_evaluate_within_budget_is_automatic():
    base = {"graph": muferro_graph(), "bindings": {"run": {"task_id": TASK}}, "parameters": {"step": 2},
            "outputs": ["payload", "energy_plot"], "profile": "web"}
    assert policy(base) == ""
    assert policy({**base, "profile": "phone", "budget": {"max_seconds": 60, "max_output_bytes": 1024**2,
                                                           "max_memory_mb": 64000}}) == ""
    assert policy({"graph": muferro_graph(), "bindings": {"run": {"task_id": TASK}}}) == ""


@pytest.mark.parametrize("change, why", [
    ({"budget": {"max_seconds": 3600}}, "计算时长"),
    ({"budget": {"max_seconds": None}}, "计算时长"),
    ({"budget": {"max_output_bytes": 512 * 1024**2}}, "输出大小"),
    ({"budget": {"max_output_bytes": None}}, "输出大小"),
    ({"profile": "desktop"}, "桌面级结果配置"),
])
def test_graph_evaluate_over_budget_goes_to_review(change, why):
    reason = policy({"graph": muferro_graph(), "bindings": {"run": {"task_id": TASK}}, **change})
    assert reason.startswith(GRAPH_REVIEW) and why in reason


def test_graph_evaluate_node_budgets_go_to_review():
    graph = muferro_graph()
    graph["nodes"][8]["params"] = {"profile": "desktop"}
    assert "桌面级渲染数据包" in policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}})
    graph["nodes"][8]["params"] = {"profile": "auto"}  # the request profile, which is checked on its own
    assert policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}}) == ""
    assert "桌面级结果配置" in policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}, "profile": "desktop"})
    graph = muferro_graph()
    graph["nodes"][8]["params"] = {"budget": {"voxels": 512 ** 3}}
    assert "渲染数据包预算" in policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}})
    graph["nodes"][8]["params"] = {"budget": {"voxels": 64 ** 3, "bytes": 1024**2}}
    assert policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}}) == ""
    graph = muferro_graph()
    graph["nodes"][10]["params"] = {"width": 8000, "height": 8000, "magnification": 2}
    assert "图像像素" in policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}})
    # An image without its own size renders at the scene's viewport.
    graph = muferro_graph()
    graph["nodes"].append({"id": "png", "type": "stk.output.image@1", "inputs": {"source": {"from": "scene.scene"}}})
    graph["outputs"]["png"] = "png.image"
    assert policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}}) == ""
    graph["nodes"][7]["params"] = {"width": 16000, "height": 9000}
    assert "图像像素" in policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}})


def test_graph_evaluate_integral_float_image_sizes_are_budgeted():
    # Integer params accept integral floats (16384.0 renders as 16384): the pixel budget must count them.
    graph = muferro_graph()
    graph["nodes"][10]["params"] = {"width": 16384.0, "height": 16384.0, "magnification": 8.0}
    assert "图像像素" in policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}})
    graph["nodes"][10]["params"] = {"width": 4000.0, "height": 2000.0, "magnification": 1.0}
    assert policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}}) == ""
    graph = muferro_graph()
    graph["nodes"].append({"id": "png", "type": "stk.output.image@1", "inputs": {"source": {"from": "scene.scene"}}})
    graph["outputs"]["png"] = "png.image"
    graph["nodes"][7]["params"] = {"width": 16000.0, "height": 9000.0}
    assert "图像像素" in policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}})
    # Integer params take integral floats as integers and refuse other numbers.
    from suan.graph.catalog import default_registry
    from suan.graph.schema import validate_graph
    image_type = default_registry()["stk.output.image@1"]
    normalized = image_type.normalize_params({"width": 400.0, "magnification": 2.0})
    assert normalized["width"] == 400 and type(normalized["width"]) is int and type(normalized["magnification"]) is int
    graph = muferro_graph()
    graph["nodes"][10]["params"] = {"width": 400.5}
    assert [i.code for i in validate_graph(graph, default_registry()) if i.severity == "error"] == ["invalid_param"]
    # Sizes the policy cannot compute fail closed (a node type unknown to the hub skips validation).
    from suan.control.policy import _payload_budget_reasons
    for bad in ("16384", float("nan"), float("inf"), True, [16384]):
        broken = muferro_graph()
        broken["nodes"][10]["params"] = {"width": bad, "height": 100}
        assert "图像像素" in _payload_budget_reasons(broken, {}), bad


def test_graph_evaluate_plot_pixels_are_budgeted():
    # A plot delivered as PNG is a raster of size_in x dpi (x magnification^2 through stk.output.image).
    graph = muferro_graph()
    graph["nodes"][9]["params"].update(size_in=[54, 54], dpi=1200)
    request = {"graph": graph, "bindings": {"run": {"task_id": TASK}}, "outputs": ["energy_plot"]}
    assert "图像像素" in policy({**request, "plot_format": "png"})
    assert policy({**request, "plot_format": "svg"}) == ""  # vector output
    assert policy({**request, "outputs": ["payload"], "plot_format": "png"}) == ""  # the plot is not delivered
    graph["nodes"][10]["params"] = {}  # the image takes the plot's size_in x dpi
    assert "图像像素" in policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}, "outputs": ["energy_png"]})
    graph["nodes"][10]["params"] = {"width": 800, "height": 600}  # its own size wins
    assert policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}, "outputs": ["energy_png"]}) == ""
    graph["nodes"][10]["params"] = {"width": 4000, "height": 3000, "magnification": 4}
    assert "图像像素" in policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}, "outputs": ["energy_png"]})
    graph["nodes"][10]["params"] = {"format": "svg"}
    assert policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}, "outputs": ["energy_png"]}) == ""
    assert policy({"preset": "energy-plot", "bindings": {"run": {"task_id": TASK}}, "plot_format": "png"}) == ""


def test_graph_validation_of_long_chains_never_recurses():
    from suan.graph.catalog import default_registry
    from suan.graph.schema import validate_graph

    def chain(n):
        nodes = [{"id": "run", "type": "stk.source.muferro_run@1", "params": {"binding": "run"}},
                 {"id": "f", "type": "stk.source.muferro_frame@1", "inputs": {"frames": {"from": "run.frames"}}}]
        for i in range(n):
            nodes.append({"id": f"c{i}", "type": "stk.filter.crop@1",
                          "inputs": {"in": {"from": f"{nodes[-1]['id']}.out"}}})
        return {"schema": "stk.graph/1", "nodes": nodes, "outputs": {"o": f"{nodes[-1]['id']}.out"}}
    issues = validate_graph(chain(1200), default_registry())  # was a RecursionError (hub 500)
    assert [i.code for i in issues] == ["too_large"]
    assert not [i for i in validate_graph(chain(190), default_registry()) if i.severity == "error"]
    with pytest.raises(ValueError, match="too_large"):
        policy({"graph": chain(1200), "bindings": {"run": {"task_id": TASK}}})


def test_graph_evaluate_unknown_node_types_go_to_review():
    graph = muferro_graph()
    graph["nodes"].append({"id": "private", "type": "mupro.analysis.vo2_classify@1",
                           "inputs": {"in": {"from": "polar.out"}}})
    reason = policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}})
    assert "未安装的节点类型" in reason and "mupro.analysis.vo2_classify@1" in reason and GRAPH_REVIEW not in reason
    # A link from the unknown node's ports cannot be checked either: still a review, not a refusal.
    graph["nodes"].append({"id": "shown", "type": "stk.render.surface@1", "inputs": {"in": {"from": "private.out"}}})
    graph["nodes"][7]["inputs"]["layers"].append({"from": "shown.layer"})
    both = policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}, "budget": {"max_seconds": 900}})
    assert both.startswith(GRAPH_REVIEW) and "计算时长" in both and "vo2_classify" in both


@pytest.mark.parametrize("payload, message", [
    ({"graph": muferro_graph(), "bindings": {"run": {"path": "/data/run"}}}, "task_id"),
    ({"graph": muferro_graph(), "bindings": {"run": "/data/run"}}, "task_id"),
    ({"graph": muferro_graph(), "bindings": {"run": {"task_id": "../../etc"}}}, "32 lowercase"),
    ({"graph": muferro_graph(), "preset": "muferro-domains"}, "exactly one"),
    ({}, "exactly one"),
    ({"graph": muferro_graph(), "extra": 1}, "Unknown request key"),
    ({"graph": muferro_graph(), "outputs": ["nope"]}, "Unknown graph output"),
    ({"graph": muferro_graph(), "profile": "tv"}, "profile"),
    ({"graph": muferro_graph(), "budget": {"max_seconds": -1}}, "positive"),
    ({"graph": muferro_graph(), "parameters": {"view": "sideways"}}, "Invalid graph"),
    ({"graph": muferro_graph(), "parameters": {"nope": 1}}, "unknown_parameter"),
    ({"graph": {"schema": "stk.graph/1", "nodes": [], "outputs": {}}}, "no_outputs"),
    ({"graph": {"schema": "stk.graph/1", "nodes": 5, "outputs": {"a": "b.c"}}}, "Invalid graph"),
    ({"preset": "no-such-preset"}, "Unknown preset"),
    ({"graph": muferro_graph(), "accept": "stk.payload/2"}, "accept"),
    ({"graph": {**muferro_graph(), "description": "x" * 600_000}}, "limited to"),
])
def test_graph_evaluate_invalid_requests_are_refused(payload, message):
    with pytest.raises(ValueError, match=message):
        policy(payload)


def test_graphs_never_carry_filesystem_paths():
    graph = muferro_graph()
    for bad in ("/home/user/run", "../elsewhere", "~/run", "C:/runs", "a\\b"):
        graph["nodes"][0]["params"]["case_dir"] = bad
        # The node's path schema or the hub's own binding-path rule refuses it.
        with pytest.raises(ValueError, match="relative to its binding|does not match pattern"):
            policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}})
    graph["nodes"][0]["params"]["case_dir"] = "case16"
    assert policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}}) == ""
    # A path given through a graph parameter is checked after substitution.
    graph = muferro_graph()
    graph["parameters"].append({"name": "folder", "type": "string", "default": "."})
    graph["nodes"][0]["params"]["case_dir"] = {"$param": "folder"}
    assert policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}}) == ""
    for bad in ("/etc", "~root"):
        with pytest.raises(ValueError, match="relative to its binding|does not match pattern|param_ref_type"):
            policy({"graph": graph, "bindings": {"run": {"task_id": TASK}}, "parameters": {"folder": bad}})


def test_task_events_and_graph_meta_payloads():
    def check(kind, payload):
        return validate_action({"id": "b" * 32, "node_id": NODE, "kind": kind, "payload": payload}, {})
    assert check("task.events", {"task_id": TASK}) == ""
    assert check("task.events", {"task_id": TASK, "offset": 4096, "limit": 65536}) == ""
    for bad in ({}, {"task_id": "x"}, {"task_id": TASK, "offset": -1}, {"task_id": TASK, "offset": True},
                {"task_id": TASK, "limit": 0}, {"task_id": TASK, "limit": 2 * 1024**2}, {"task_id": TASK, "path": "a"}):
        with pytest.raises(ValueError):
            check("task.events", bad)
    assert check("graph.meta", {}) == "" and check("graph.meta", {"include": ["catalog", "render"]}) == ""
    for bad in ({"include": ["secrets"]}, {"include": "catalog"}, {"other": 1}):
        with pytest.raises(ValueError):
            check("graph.meta", bad)


def test_hub_validation_runs_without_numpy(tmp_path):
    pytest.importorskip("fastapi")
    code = """
import json, sys
sys.modules['numpy'] = None
from fastapi.testclient import TestClient
from suan.control.app import create_app
from test_control_graph import muferro_graph, OWNER, AUTH
app = create_app(sys.argv[1], OWNER)
with TestClient(app) as http:
    code = http.post('/api/v1/pairings', json={'role': 'node'}, headers=AUTH).json()['code']
    node = http.post('/api/v1/pairings/claim', json={'code': code, 'name': 'n'}).json()['device_id']
    body = {'id': 'a' * 32, 'node_id': node, 'kind': 'graph.evaluate',
            'payload': {'graph': muferro_graph(), 'bindings': {'run': {'task_id': 'd' * 32}}}}
    stored = http.post('/api/v1/actions', json=body, headers=AUTH)
    assert stored.status_code == 202 and stored.json()['state'] == 'queued', stored.text
    body['id'] = 'b' * 32
    body['payload']['parameters'] = {'view': 'sideways'}
    refused = http.post('/api/v1/actions', json=body, headers=AUTH)
    assert refused.status_code == 400 and 'Invalid graph' in refused.json()['detail'], refused.text
    assert http.get('/api/v1/graphs/catalog', headers=AUTH).json()['nodes']
    assert isinstance(http.get('/api/v1/graphs/presets', headers=AUTH).json(), list)
assert sys.modules['numpy'] is None
heavy = sorted(m for m in ('vtk', 'vtkmodules', 'matplotlib', 'h5py') if m in sys.modules)
assert not heavy, heavy
print('numpy-free ok')
"""
    tests = os.path.dirname(os.path.abspath(__file__))
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": os.pathsep.join([tests, os.environ.get("PYTHONPATH", "")])}
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path / "hub")], capture_output=True, text=True,
                            env=env, cwd=tmp_path, timeout=120)
    assert result.returncode == 0, result.stderr[-3000:]
    assert "numpy-free ok" in result.stdout


# ---------------------------------------------------------------------------
# Agent lanes (no network)


class FakeSocket:
    """A hub connection: queued incoming frames, recorded outgoing messages, and a check that sends never overlap."""

    def __init__(self):
        self.incoming = asyncio.Queue()
        self.sent = []
        self.sending = False

    async def send(self, text):
        assert not self.sending, "concurrent websocket sends"
        self.sending = True
        await asyncio.sleep(0.001)
        self.sent.append(json.loads(text))
        self.sending = False

    def push(self, message):
        self.incoming.put_nowait(None if message is None else json.dumps(message))

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.incoming.get()
        if item is None:
            raise StopAsyncIteration
        return item

    def results(self):
        return [m for m in self.sent if m["type"] == "result"]


def test_agent_lanes_dedup_and_reconnect(tmp_path):
    from suan.control.agent import NodeAgent

    class Agent(NodeAgent):
        def __init__(self):
            super().__init__(None, tmp_path / "agent", graph_workers=1)
            self.gates, self.runs, self.active, self.peak = {}, [], 0, 0
            self.guard = threading.Lock()

        def snapshot(self):
            return {"tasks": []}

        def execute(self, action):
            with self.guard:
                self.runs.append(action["id"])
                if action["kind"] == "graph.evaluate":
                    self.active += 1
                    self.peak = max(self.peak, self.active)
            if action["kind"] == "graph.evaluate":
                self.gates.setdefault(action["id"], threading.Event()).wait(10)
                with self.guard:
                    self.active -= 1
                return {"schema": "stk.graph-result/1", "id": action["id"]}
            return {"fast": action["id"]}

    def action(kind, identity=None):
        return {"id": identity or uuid.uuid4().hex, "kind": kind, "payload": {}}

    async def until(predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while not predicate():
            assert time.monotonic() < deadline
            await asyncio.sleep(0.01)

    async def scenario():
        agent = Agent()
        first = FakeSocket()
        serving = asyncio.create_task(agent.serve(first))
        g1, g2, fast = action("graph.evaluate"), action("graph.evaluate"), action("task.logs")
        for gate in (g1, g2):
            agent.gates[gate["id"]] = threading.Event()
        first.push({"type": "action", "action": g1})
        first.push({"type": "action", "action": g2})
        first.push({"type": "action", "action": fast})
        first.push({"type": "action", "action": g1})  # dispatched again while running: not started twice
        first.push({"type": "ping"})  # unknown frames are ignored
        # The fast lane is not blocked by the graph lane.
        await until(lambda: [r["id"] for r in first.results()] == [fast["id"]])
        assert agent.runs.count(g1["id"]) == 1 and g2["id"] not in agent.runs  # one graph at a time
        # The connection drops while g1 runs; the hub re-dispatches it on the next connection.
        first.push(None)
        await serving
        second = FakeSocket()
        serving = asyncio.create_task(agent.serve(second))
        second.push({"type": "action", "action": g1})
        agent.gates[g1["id"]].set()
        await until(lambda: g1["id"] in [r["id"] for r in second.results()])
        agent.gates[g2["id"]].set()
        await until(lambda: g2["id"] in [r["id"] for r in second.results()])
        assert agent.runs.count(g1["id"]) == 1 and agent.runs.count(g2["id"]) == 1 and agent.peak == 1
        assert [r["id"] for r in first.results()] == [fast["id"]]
        assert second.results()[0]["result"] == {"schema": "stk.graph-result/1", "id": g1["id"]}
        assert any(m["type"] == "snapshot" for m in second.sent)
        # Finished actions can run again (a lost result): the durable cache answers real agents.
        second.push({"type": "action", "action": fast})
        await until(lambda: [r["id"] for r in second.results()].count(fast["id"]) == 1)
        second.push(None)
        await serving
        assert agent._inflight == {}

    asyncio.run(scenario())


def test_agent_reports_errors_and_needs_a_blob_channel(tmp_path):
    from suan.control.agent import NodeAgent

    class Runtime:
        def health(self):
            return {"features": []}

        def events(self, task_id, offset=0, limit=None):
            from suan.runtime.client import RuntimeErrorResponse
            raise RuntimeErrorResponse(404, "Not found")

    agent = NodeAgent(Runtime(), tmp_path / "agent")
    graph = {"id": "a" * 32, "kind": "graph.evaluate", "payload": {"graph": muferro_graph()}}
    with pytest.raises(ValueError, match="blob upload channel"):
        agent.execute(graph)
    agent.blob_sink = lambda data: hashlib.sha256(data).hexdigest()
    agent.hub_features = set()
    with pytest.raises(ValueError, match="does not accept result blobs"):
        agent.execute(graph)
    with pytest.raises(ValueError, match="monitoring events"):
        agent.execute({"id": "b" * 32, "kind": "task.events", "payload": {"task_id": TASK}})
    agent.hub_features = {"blobs"}
    broken = copy.deepcopy(graph)
    broken["payload"]["parameters"] = {"view": "sideways"}
    with pytest.raises(ValueError, match="invalid_param|param_ref_type|invalid_parameter"):
        agent.execute(broken)
    assert not list((tmp_path / "agent").glob("*.json"))  # failures are never cached


def test_concurrent_downloads_of_one_artifact_are_serialized(tmp_path):
    # The agent's fast lane runs view.build and view.probe of one artifact at once: both download to
    # <cache>/fields/<sha><suffix> through the same resumable .part file.
    from urllib.parse import parse_qs, urlsplit
    from suan.runtime.client import RuntimeClient
    data = os.urandom(3 * 1024 * 1024 + 17)
    item = {"path": "Polar.00000000.dat", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    class Runtime(RuntimeClient):
        def __init__(self):
            pass

        def artifacts(self, task_id):
            return [dict(item)]

        def request(self, method, path, data_=None, binary=False):
            query = parse_qs(urlsplit(path).query)
            offset, limit = int(query["offset"][0]), int(query["limit"][0])
            time.sleep(0.02)  # a network hop: the downloads interleave
            return data[offset:offset + limit]

    target = tmp_path / "fields" / (item["sha256"] + ".dat")
    results, errors = [], []

    def fetch():
        try:
            results.append(Runtime().download(TASK, item["path"], target))
        except Exception as exc:  # pragma: no cover - the regression
            errors.append(exc)
    threads = [threading.Thread(target=fetch) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert not errors and results == [target] * 4
    assert target.read_bytes() == data and sorted(p.name for p in target.parent.iterdir()) == [target.name]


def test_agent_errors_never_carry_host_paths(tmp_path):
    from suan.control.agent import NodeAgent
    agent = NodeAgent(None, tmp_path / "agent")
    part = tmp_path / "agent" / "fields" / "abc.dat.part"
    message = agent.public_error(FileNotFoundError(2, "No such file or directory", str(part), str(part) + ".x"))
    assert message == "FileNotFoundError: No such file or directory" and str(tmp_path) not in message
    message = agent.public_error(RuntimeError(f"cannot read {tmp_path / 'agent' / 'fields' / 'x.dat'}"))
    assert str(tmp_path) not in message and "<agent cache>" in message
    assert agent.public_error(ValueError("Select a completed task's published field artifact")) == \
        "Select a completed task's published field artifact"


# ---------------------------------------------------------------------------
# End to end: fake muFerro under the Runtime -> hub -> agent -> blobs


@pytest.fixture
def fake_sdk(tmp_path, monkeypatch):
    from mupro_fake import make_fake_sdk
    for key in [*NODE_ENV, *(key for key in os.environ if key.startswith("I_MPI_"))]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MUPRO_SDK_PREFIX", str(make_fake_sdk(tmp_path / "sdk")))


def muferro_task(client, supervisor):
    from conftest import finish
    from suan.control.templates import MUFERRO_EXAMPLE_TEMPLATE
    workspace = client.create_workspace("图谱测试")["id"]
    task = client.submit({**MUFERRO_EXAMPLE_TEMPLATE, "workspace_id": workspace, "name": "muferro-example"})
    assert finish(client, supervisor, task["id"], timeout=60)["state"] == "succeeded"
    return task["id"]


def hub_transport(http):
    def send(method, path, body, headers):
        if hasattr(body, "read"):
            body = body.read()
        return http.request(method, path, content=body, headers=headers).status_code
    return send


def check_graph_result(result, fetch):
    """Every blob the result names is served, and the payload validates against its buffers."""
    from suan.render.payload import decode
    assert result["schema"] == "stk.graph-result/1" and len(result["graph_sha256"]) == 64
    assert result["parameters"]["step"] == {"value": 2, "choices": [0, 2]}
    outputs = result["outputs"]
    payload = outputs["payload"]
    assert payload["type"] == "payload"
    manifest = payload["manifest"]
    assert all(b["uri"] == "sha256:" + b["sha256"] for b in manifest["buffers"])
    decoded = decode(manifest, fetch)
    assert decoded.manifest["schema"] == "stk.payload/2"
    assert {layer["type"] for layer in manifest["layers"]} >= {"volume", "lines"}
    plot = outputs["energy_plot"]
    assert plot["type"] == "plot" and plot["media_type"] == "image/svg+xml"
    assert fetch(plot["blob"]).lstrip().startswith(b"<")
    assert json.loads(fetch(plot["data_blob"]))["marks"][0]["data"]["y"] == [-1.125, -2.25, -3.375]
    image = outputs["energy_png"]
    assert image["type"] == "image" and image["media_type"] == "image/png"
    assert fetch(image["blob"]).startswith(b"\x89PNG") and image["width"] == 320
    energy = outputs["energy"]
    assert energy["type"] == "table" and energy["columns"]["step"] == [1, 2, 3]
    assert energy["units"]["Total Energy"] == "normalized"
    return manifest


def test_graph_evaluate_end_to_end_through_the_hub(runtime, fake_sdk, tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("numpy")
    pytest.importorskip("matplotlib")
    from fastapi.testclient import TestClient
    from suan.control.agent import BlobUploader, NodeAgent
    from suan.control.app import create_app
    client, supervisor, _, _ = runtime
    task_id = muferro_task(client, supervisor)
    app = create_app(tmp_path / "control", OWNER)
    with TestClient(app) as http:
        code = http.post("/api/v1/pairings", json={"role": "node"}, headers=AUTH).json()["code"]
        node = http.post("/api/v1/pairings/claim", json={"code": code, "name": "节点"}).json()
        code = http.post("/api/v1/pairings", json={"role": "client"}, headers=AUTH).json()["code"]
        viewer = {"Authorization": "Bearer " + http.post("/api/v1/pairings/claim",
                                                          json={"code": code, "name": "网页"}).json()["token"]}
        uploads = []
        transport = hub_transport(http)
        sink = BlobUploader("http://127.0.0.1", node["token"],
                            transport=lambda *args: uploads.append(args[:2]) or transport(*args))
        agent = NodeAgent(client, tmp_path / "agent", blob_sink=sink)

        def run(kind, payload):
            body = {"id": uuid.uuid4().hex, "node_id": node["device_id"], "kind": kind, "payload": payload}
            stored = http.post("/api/v1/actions", json=body, headers=viewer)
            assert stored.status_code == 202 and stored.json()["state"] == "queued", stored.text
            dispatched = ws.receive_json()["action"]
            assert dispatched == body
            try:
                ws.send_json({"type": "result", "id": body["id"], "result": agent.execute(dispatched)})
            except ValueError as exc:
                ws.send_json({"type": "result", "id": body["id"], "error": str(exc)})
            deadline = time.monotonic() + 10
            while (record := http.get("/api/v1/actions/" + body["id"], headers=viewer).json())["state"] == "queued":
                assert time.monotonic() < deadline
                time.sleep(.02)
            return body, record

        with http.websocket_connect("/api/v1/nodes/connect", headers={"Authorization": "Bearer " + node["token"]}) as ws:
            request = {"graph": muferro_graph(), "bindings": {"run": {"task_id": task_id}},
                       "parameters": {"step": "latest"}, "profile": "web"}
            body, record = run("graph.evaluate", request)
            assert record["state"] == "succeeded", record["error"]

            def fetch(digest):
                response = http.get("/api/v1/blobs/" + digest, headers=viewer)
                assert response.status_code == 200
                assert response.headers["cache-control"] == "private, max-age=31536000, immutable"
                assert hashlib.sha256(response.content).hexdigest() == digest
                return response.content
            manifest = check_graph_result(record["result"], fetch)
            puts = [path for method, path in uploads if method == "PUT"]
            assert len(puts) == len(set(puts)) >= len(manifest["buffers"]) + 3
            assert all(method == "HEAD" for method, _ in uploads[::2])  # HEAD before every PUT
            assert http.get("/api/v1/blobs/" + manifest["buffers"][0]["sha256"],
                            headers={"Authorization": "Bearer " + node["token"]}).status_code == 403
            # A lost acknowledgement: the agent answers from its cache without uploading again.
            before = len(uploads)
            assert agent.execute(body) == record["result"] and len(uploads) == before
            # A camera change re-uses the cached data nodes and uploads only new buffers.
            _, moved = run("graph.evaluate", {**request, "parameters": {"step": "latest", "view": "+x"}})
            assert moved["state"] == "succeeded", moved["error"]
            assert "polar" not in moved["result"]["evaluated"] and moved["result"]["cache"]["hits"] > 0

            _, events = run("task.events", {"task_id": task_id, "offset": 0})
            assert events["state"] == "succeeded", events["error"]
            result = events["result"]
            assert result["terminal"] is True and result["next_offset"] == result["size"] > 0
            types = [event["type"] for event in result["events"]]
            assert types[0] == "run.started" and types[-1] == "run.completed" and "progress" in types
            _, later = run("task.events", {"task_id": task_id, "offset": result["next_offset"]})
            assert later["result"]["events"] == []

            _, meta = run("graph.meta", {"include": ["catalog", "presets", "features"]})
            assert meta["state"] == "succeeded", meta["error"]
            assert {n["id"] for n in meta["result"]["catalog"]["nodes"]} >= {"stk.source.muferro_run@1"}
            assert meta["result"]["features"]["agent"] == AGENT_FEATURES
            with app.state.store.db() as db:
                row = db.execute("SELECT result, result_ref FROM actions WHERE id=?", (meta["id"],)).fetchone()
            from suan.control.store import RESULT_INLINE_LIMIT, encode
            offloaded = len(encode(meta["result"]).encode()) > RESULT_INLINE_LIMIT  # grows with the catalog
            assert (row["result"] is None, bool(row["result_ref"])) == (offloaded, offloaded)

            # Node failures come back as a failed action with the node's error, not as a dropped result.
            _, failed = run("graph.evaluate", {**request, "bindings": {"run": {"task_id": "e" * 32}},
                                               "outputs": ["energy"]})
            assert failed["state"] == "failed" and failed["result"] is None
            assert "run" in failed["error"] and len(failed["error"]) <= 2000
            invalid = http.post("/api/v1/actions", headers=viewer, json={
                "id": uuid.uuid4().hex, "node_id": node["device_id"], "kind": "graph.evaluate",
                "payload": {**request, "bindings": {"run": {"dir": "/tmp"}}}})
            assert invalid.status_code == 400


def test_agent_loop_over_loopback_http_and_websocket(runtime, fake_sdk, tmp_path):
    """The real agent (outbound WebSocket, urllib blob uploads, lanes) against a loopback control server."""
    pytest.importorskip("numpy")
    pytest.importorskip("matplotlib")
    uvicorn = pytest.importorskip("uvicorn")
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("websockets")
    from suan.control.agent import NodeAgent
    from suan.control.app import create_app
    from suan.render.payload import decode
    client, supervisor, _, _ = runtime
    task_id = muferro_task(client, supervisor)
    app = create_app(tmp_path / "control", OWNER)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", access_log=False,
                                           ws_max_size=16 * 1024 * 1024))
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline
        time.sleep(.02)
    url = f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    loop = asyncio.new_event_loop()
    agent = NodeAgent(client, tmp_path / "agent", graph_workers=2)
    holder = {}

    def serve_agent():
        asyncio.set_event_loop(loop)
        holder["task"] = loop.create_task(agent.run(url, node["token"]))
        try:
            loop.run_until_complete(holder["task"])
        except asyncio.CancelledError:
            pass

    try:
        with httpx.Client(base_url=url, timeout=30) as http:
            code = http.post("/api/v1/pairings", json={"role": "node"}, headers=AUTH).json()["code"]
            node = http.post("/api/v1/pairings/claim", json={"code": code, "name": "node"}).json()
            thread = threading.Thread(target=serve_agent, daemon=True)
            thread.start()
            actions = {
                "graph": {"kind": "graph.evaluate", "payload": {
                    "graph": muferro_graph(), "bindings": {"run": {"task_id": task_id}},
                    "outputs": ["payload", "energy_plot", "energy_png", "energy"]}},
                "logs": {"kind": "task.logs", "payload": {"task_id": task_id}},
                "events": {"kind": "task.events", "payload": {"task_id": task_id}},
            }
            ids = {}
            for name, body in actions.items():
                ids[name] = uuid.uuid4().hex
                response = http.post("/api/v1/actions", headers=AUTH,
                                     json={"id": ids[name], "node_id": node["device_id"], **body})
                assert response.json()["state"] == "queued", response.text
            deadline = time.monotonic() + 90
            records = {}
            while len(records) < len(ids):
                assert time.monotonic() < deadline, records
                for name, identity in ids.items():
                    record = http.get("/api/v1/actions/" + identity, headers=AUTH).json()
                    if record["state"] != "queued":
                        records[name] = record
                time.sleep(.1)
            assert all(r["state"] == "succeeded" for r in records.values()), {k: r["error"] for k, r in records.items()}
            assert agent.hub_features >= {"blobs", "graph"}

            def fetch(digest):
                response = http.get("/api/v1/blobs/" + digest, headers=AUTH)
                assert response.status_code == 200
                return response.content
            check_graph_result(records["graph"]["result"], fetch)
            decode(records["graph"]["result"]["outputs"]["payload"]["manifest"], fetch)
            assert records["events"]["result"]["terminal"] is True
            device = next(d for d in http.get("/api/v1/devices", headers=AUTH).json() if d["id"] == node["device_id"])
            assert device["online"] and device["snapshot"]["features"] == AGENT_FEATURES
    finally:
        if "task" in holder:
            loop.call_soon_threadsafe(holder["task"].cancel)
        server.should_exit = True
        server_thread.join(timeout=10)
