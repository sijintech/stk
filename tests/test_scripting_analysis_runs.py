"""The scripting facade pins its project session and keeps every execution action explicit."""
from copy import deepcopy

from suan.scripting import API
from test_analysis_run_contract import IDENTITY, prepared_run


def test_analysis_run_facade_keeps_handle_and_never_dispatches_while_reading():
    calls = []
    run = prepared_run()
    def call(method, params):
        calls.append((method, deepcopy(params)))
        if method.endswith(".list"):
            return {"runs": [], "next_offset": None}
        if method.endswith(".result"):
            return {"run": run, "result": {"schema": "stk.graph-result/1", "outputs": {}}, "blob_dir": "/archive/blobs"}
        return {"run": run}
    api = API(call)
    api._project_handle = "a" * 32
    saved = api.project.analysis_runs
    mapping = {"data": {"fields/signed.dat": IDENTITY}}
    assert saved.prepare(IDENTITY, IDENTITY, mapping, run_id=IDENTITY, expected_revision=4) == run
    assert calls[-1] == ("project.analysis_runs.prepare", {"handle": "a" * 32, "analysis_id": IDENTITY,
        "snapshot_id": IDENTITY, "bindings": mapping, "run_id": IDENTITY, "expected_revision": 4})
    api._project_handle = "b" * 32
    saved.get(IDENTITY)
    assert saved.list() == {"runs": [], "next_offset": None}
    assert saved.result(IDENTITY)["result"]["outputs"] == {}
    assert all(method != "project.analysis_runs.start" for method, _ in calls)
    assert all(params["handle"] == "a" * 32 for _, params in calls)
    before = len(calls)
    for operation in (saved.start, saved.cancel, saved.recover):
        assert operation(IDENTITY) == run
    assert [method for method, _ in calls[before:]] == [
        "project.analysis_runs.start", "project.analysis_runs.cancel", "project.analysis_runs.recover"]
    assert all(params["run_id"] == IDENTITY and params["handle"] == "a" * 32 for _, params in calls[before:])
    assert len(calls) == before + 3
