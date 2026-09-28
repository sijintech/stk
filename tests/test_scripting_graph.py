"""Console graph operations use the shared service and keep execution ownership explicit."""
from pathlib import Path
import time

import pytest

from suan.desktop_bridge.graph_worker import GraphWorker
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_desktop_scripts import scripts, execute, settled  # noqa: F401
from test_desktop_graph_worker import worker_command, work  # noqa: F401


def test_real_console_catalog_validation_and_graph_errors(scripts):
    session = scripts.call("script.open")["session"]
    result = execute(scripts, session, '''
import copy
catalog = stk.graph.catalog()
assert any(node['id'] == 'stk.source.muferro_run@1' for node in catalog['nodes'])
preset = next(p for p in stk.graph.presets() if p['id'] == 'muferro-domains')
graph = copy.deepcopy(preset['graph'])
assert stk.graph.validate(graph)['ok']
graph['nodes'][0]['type'] = 'stk.source.no_such_node@1'
issues = stk.graph.validate(graph)
assert not issues['ok'] and issues['issues'][0]['code'] == 'unknown_type'
assert stk.graph.cancel('never-started') == {'cancelled': False}
assert stk.graph.ensure_blobs(['0' * 64])['missing'] == ['0' * 64]
assert stk.graph.colormaps()['aliases']['grey'] == 'gray'
from suan.scripting import ScriptError
try:
    stk.graph.evaluate({'preset': 'no-such'}, eval_id='bad')
except ScriptError as error:
    assert error.code == 'graph_error' and error.data['graph_code'] == 'unknown_preset'
else:
    raise AssertionError('invalid graph was accepted')
try:
    stk.graph.evaluate({'preset': 'muferro-domains'}, eval_id='bad-hub', mode='hub')
except ScriptError as error:
    assert error.code == 'invalid_params'
else:
    raise AssertionError('Hub target was not required')
''')
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    assert not scripts.violations


def test_real_console_evaluates_custom_graph_blobs_and_original_grid_probe(scripts, tmp_path):
    np = pytest.importorskip("numpy")
    pytest.importorskip("vtk")
    pytest.importorskip("matplotlib")
    from mupro_fake import write_domain_run
    root = tmp_path / "域 run"
    frames = write_domain_run(root, grid=(8, 7, 6), steps=2, interval=1)
    session = scripts.call("script.open")["session"]
    result = execute(scripts, session, f'''
import hashlib
from pathlib import Path
root = {str(root)!r}
preset = next(p for p in stk.graph.presets() if p['id'] == 'muferro-domains')
# Pass an editable graph document rather than requiring a shipped preset ID.
graph = preset['graph']
assert stk.graph.validate(graph, parameters={{'step': 'latest'}})['ok']
response = stk.graph.evaluate({{'graph': graph, 'outputs': ['view', 'fractions'],
                               'parameters': {{'step': 'latest'}}}},
                              eval_id='console-analysis', local_bindings={{'run': root}})
result = response['result']
assert result['schema'] == 'stk.graph-result/1'
assert result['parameters']['step']['value'] == 2
assert result['outputs']['fractions']['type'] == 'table'
manifest = result['outputs']['view']['manifest']
digests = [buffer['sha256'] for buffer in manifest['buffers']]
blobs = stk.graph.ensure_blobs(digests)
assert not blobs['missing']
for digest, blob in blobs['blobs'].items():
    assert hashlib.sha256(Path(blob['path']).read_bytes()).hexdigest() == digest
layer = next(layer for layer in manifest['layers'] if layer['id'] == 'surface_layer')
sample = stk.graph.probe(layer['pick']['probe'], graph=graph,
    context={{'values': {{'step': 'latest'}}, 'result': result}},
    local_bindings={{'run': root}}, position=[3.0, 4.0, 5.0])
assert sample['target']['path'] == 'Polar.00000002.dat'
import json
Path({str(tmp_path / 'sample.json')!r}).write_text(json.dumps(sample['sample']['values']))
''')
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    import json
    assert np.allclose(json.loads((tmp_path / "sample.json").read_text()), frames[2][3, 4, 5])
    assert not scripts.violations


def test_console_interrupt_cancels_its_active_local_graph_and_recovers(inproc, worker_command):
    harness = inproc()
    harness.bridge.graphs.worker.close()
    harness.bridge.graphs.worker = GraphWorker(harness.bridge.cache_dir, command=worker_command)
    session = harness.call("script.open")["session"]
    harness.call("script.execute", {"session": session, "source":
        "stk.graph.evaluate({'preset': 'slice', 'parameters': {'mode': 'block'}}, eval_id='owned')"})
    harness.wait_event(lambda event: event["event"] == "graph.progress" and event["data"]["eval_id"] == "owned")
    child = harness.bridge.graphs.worker._child
    assert harness.call("script.interrupt", {"session": session})["interrupted"]
    assert settled(harness, session)["run"]["state"] == "cancelled"
    assert child.process.poll() is not None and not harness.bridge.graphs.running
    assert execute(harness, session, "assert stk.graph.cancel('owned') == {'cancelled': False}")["run"]["state"] == "succeeded"
    assert not harness.violations


def test_interrupting_queued_console_graph_keeps_unrelated_active_evaluation(inproc, worker_command):
    harness = inproc()
    harness.bridge.graphs.worker.close()
    harness.bridge.graphs.worker = GraphWorker(harness.bridge.cache_dir, command=worker_command)
    active = harness.request("graph.evaluate", {"eval_id": "native", **work("block")})
    harness.wait_event(lambda event: event["event"] == "graph.progress" and event["data"]["eval_id"] == "native")
    child = harness.bridge.graphs.worker._child
    session = harness.call("script.open")["session"]
    harness.call("script.execute", {"session": session, "source":
        "stk.graph.evaluate({'preset': 'slice'}, eval_id='queued-console')"})
    deadline = time.monotonic() + 10
    while "queued-console" not in harness.bridge.graphs.running:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    harness.call("script.interrupt", {"session": session})
    assert settled(harness, session)["run"]["state"] == "cancelled"
    assert child.process.poll() is None and set(harness.bridge.graphs.running) == {"native"}
    assert harness.call("graph.cancel", {"eval_id": "native"})["cancelled"]
    assert harness.response(active)["error"]["code"] == "cancelled"
    assert not harness.violations
