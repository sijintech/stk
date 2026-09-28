"""The shipped desktop example prepares without execution and collects real Runtime outputs."""
import json
from pathlib import Path

import pytest

from conftest import finish
from examples.project_scan.solver import simulate
from suan.project import ProjectStore
from test_desktop_scripts import scripts, execute  # noqa: F401
from test_desktop_bridge import bridge_env  # noqa: F401
from test_desktop_bridge_runtime import add_profile


def test_synthetic_field_metrics_and_portable_outputs(tmp_path):
    metrics = simulate({"temperature_K": 300, "size": 5}, tmp_path)
    assert metrics["shape"] == [5] * 3 and metrics["synthetic"]
    assert metrics["max_K"] == 300 and 0 < metrics["mean_K"] < 300
    vtk = (tmp_path / "field.vtk").read_text().split("LOOKUP_TABLE default\n")
    values = list(map(float, vtk[1].split()))
    assert len(values) == 125 and max(values) == 300
    assert sum(values) / len(values) == pytest.approx(metrics["mean_K"])
    assert (tmp_path / "slice.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert json.loads((tmp_path / "metrics.json").read_text())["temperature_K"] == 300


def test_prepare_submit_collect_example_preserves_run_provenance(scripts, runtime, tmp_path):
    client, supervisor, _, _ = runtime
    connection = add_profile(scripts, runtime)
    directory = tmp_path / "scan-project"
    session = scripts.call("script.open", {"directory": str(tmp_path)})["session"]
    source = f'''
from examples.project_scan.prepare import prepare
from examples.project_scan.collect import collect
scan = prepare(stk, {str(directory)!r}, {connection!r}, [300, 350], show_ui=False)
p = stk.projects.open(scan['directory'])
assert len(p.runs.list()['runs']) == 2
assert stk.runtime({connection!r}).tasks.list() == []
assert collect(stk, p) == []
for run_id in scan['run_ids']:
    assert p.runs.submit(run_id)['status']['task']['state'] == 'queued'
'''
    result = execute(scripts, session, source)
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})
    for task in client.tasks():
        assert finish(client, supervisor, task["id"])["state"] == "succeeded"
    result = execute(scripts, session, "results = collect(stk, p)\nassert len(results) == 2\nassert results[1]['metrics']['max_K'] == 350\nassert collect(stk, p) == results")
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})
    store = ProjectStore(directory)
    model = store.snapshot()
    result_table = next(table for table in model["tables"] if table["name"] == "Results / 结果比较")
    assert len(result_table["records"]) == 2
    assert len(client.tasks()) == 2
    assert all(run["parameter_state"] == "current" for run in store.runs.list()["runs"])
    assert all(run["task_state"] == "succeeded" for run in store.runs.list()["runs"])
    assert len(store.files.list()["records"]) == 9  # 1 program + 2 configs + 2 * 3 outputs
    vtk_paths = sorted(directory.glob("results/*/field.vtk"))
    assert len(vtk_paths) == 2
    # An independent VTK reader validates the exported dimensions and scalar layout when installed.
    try:
        import vtk
    except ImportError:
        vtk = None
    for path in vtk_paths if vtk else []:
        reader = vtk.vtkStructuredPointsReader()
        reader.SetFileName(str(path))
        reader.Update()
        assert reader.GetOutput().GetDimensions() == (17, 17, 17)
        assert reader.GetOutput().GetPointData().GetScalars().GetNumberOfTuples() == 17 ** 3

    result = execute(scripts, session, "from pathlib import Path\nPath(results[0]['paths'][1]).write_bytes(b'changed locally')\ntry:\n    collect(stk, p)\nexcept ValueError as error:\n    assert 'changed locally' in str(error)\nelse:\n    raise AssertionError('must not collect changed local outputs')")
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})
    assert len(client.tasks()) == 2
