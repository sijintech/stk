"""The local desktop demo is useful on macOS/Windows without installing a Linux task server."""
import json
from pathlib import Path

import pytest

from suan.project import ProjectStore
from test_desktop_bridge import bridge_env  # noqa: F401
from test_desktop_scripts import scripts, execute  # noqa: F401


@pytest.mark.parametrize("analyze", [False, True])
def test_offline_demo_creates_typed_project_frozen_inputs_and_independent_local_results(scripts, tmp_path, analyze):
    if analyze:
        pytest.importorskip("vtk")
    session = scripts.call("script.open")["session"]
    directory = tmp_path / "离线演示"
    source = f'''
from examples.project_scan.offline import create_demo
assert all(connection["id"] == "local" for connection in stk.connections.list())
demo = create_demo(stk, {str(directory)!r}, show_ui=False, analyze={analyze!r})
p = stk.projects.open(demo['directory'])
assert p.runs.list()['runs'] == []
assert all(connection["id"] == "local" for connection in stk.connections.list())
assert p.snapshots.verify(demo['snapshot_id'])['ok']
'''
    result = execute(scripts, session, source)
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    store = ProjectStore(directory)
    model = store.snapshot()
    cases = next(table for table in model["tables"] if table["name"] == "Cases / 参数")
    effective = next(field["id"] for field in cases["fields"] if field["name"] == "Effective temperature")
    assert [record["values"][effective] for record in cases["records"]] == [310, 335, 360]
    assert all(record["evaluations"][effective]["state"] == "ok" for record in cases["records"])
    files = store.files.list()["records"]
    assert any(record["name"] == "analysis.graph.json" for record in files)
    paths = sorted(directory.glob("results/*/field.vtk"))
    assert len(paths) == 3
    metrics = [json.loads(path.with_name("metrics.json").read_text()) for path in paths]
    assert [item["max_K"] for item in metrics] == [310, 335, 360]
    assert all(path.with_name("analysis.json").is_file() for path in paths) == analyze
    # Preview the shared edit through the real worker before committing it. The candidate includes
    # recomputed cross-table values, but the original database, input objects and results stay put.
    result = execute(scripts, session, '''
before = p.snapshot()
proposal = p.preview([{'op':'set_cell', 'table_id':demo['control_table'], 'record_id':demo['control_record'],
                       'field_id':demo['offset_field'], 'value':20}], expected_revision=before['project']['revision'])
assert proposal['persisted'] is False
assert p.snapshot() == before
candidate = next(table for table in proposal['snapshot']['tables'] if table['id'] == demo['table_id'])
assert [row['values'][demo['effective_field']] for row in candidate['records']] == [320, 345, 370]
assert p.snapshots.verify(demo['snapshot_id'])['ok']
''')
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    assert store.snapshot() == model
    # A separate, explicit operation applies the reviewed commands and checks their base revision.
    result = execute(scripts, session, '''
p.apply(proposal['commands'], expected_revision=proposal['base_revision'])
''')
    assert result["run"]["state"] == "succeeded"
    cases = next(table for table in store.snapshot()["tables"] if table["id"] == cases["id"])
    assert [record["values"][effective] for record in cases["records"]] == [320, 345, 370]
    assert [json.loads(path.with_name("metrics.json").read_text())["max_K"] for path in paths] == [310, 335, 360]
    assert not scripts.violations
