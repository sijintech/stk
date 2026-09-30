"""Analysis-run wire structure is bounded and agrees with the independent JSON Schema validator."""
from copy import deepcopy

import pytest

from suan.desktop_bridge.schema import method_contract, validate_params, validate_outgoing
from suan.graph.schema import check_value


IDENTITY = "11111111-1111-4111-8111-111111111111"
HANDLE = "a" * 32
DIGEST = "b" * 64


def prepared_run():
    return {
        "id": IDENTITY, "project_id": IDENTITY, "source_revision": 4,
        "created_at": "2026-09-30T10:00:00+00:00", "analysis_id": IDENTITY,
        "analysis_name": "有符号场", "document": {
            "format": "stk.analysis-document/1",
            "graph": {"schema": "stk.graph/1", "nodes": [{"id": "source", "type": "stk.source.file@1"}],
                      "outputs": {"data": "source.data"}},
            "parameters": {"unit": None, "integer": 1, "float": 1.0}, "outputs": [],
        },
        "snapshot_id": IDENTITY, "snapshot_sha256": DIGEST,
        "bindings": {"data": {"fields/signed.dat": {"record_id": IDENTITY, "sha256": DIGEST, "size": 42}}},
        "profile": "desktop", "budget": {"max_seconds": 300, "max_output_bytes": 268435456},
        "plan_sha256": DIGEST, "status": "prepared", "updated_at": "2026-09-30T10:00:00+00:00",
        "started_at": None, "finished_at": None, "cancel_requested_at": None, "executor_id": None,
        "error": None, "result": None,
    }


def preparation():
    return {"handle": HANDLE, "analysis_id": IDENTITY, "snapshot_id": IDENTITY,
            "bindings": {"data": {"fields/signed.dat": IDENTITY}}, "run_id": IDENTITY,
            "expected_revision": 4}


def agrees(method, part, value, valid):
    contract = method_contract(method)[part]
    assert (not check_value(value, contract)) is valid
    jsonschema = pytest.importorskip("jsonschema")
    assert jsonschema.Draft202012Validator(contract).is_valid(value) is valid


def test_run_contract_accepts_raw_null_and_empty_output_selection_without_coercion():
    run = prepared_run()
    before = deepcopy(run)
    for method in ("prepare", "get", "start", "cancel", "recover"):
        name = "project.analysis_runs." + method
        params = preparation() if method == "prepare" else {"handle": HANDLE, "run_id": IDENTITY}
        agrees(name, "params", params, True)
        agrees(name, "result", {"run": run}, True)
        assert validate_outgoing({"id": 1, "result": {"run": run}}, name) == []
    assert run == before
    assert type(run["document"]["parameters"]["integer"]) is int
    assert type(run["document"]["parameters"]["float"]) is float
    summary = {key: value for key, value in run.items() if key not in ("document", "bindings")}
    agrees("project.analysis_runs.list", "result", {"runs": [summary], "next_offset": None}, True)
    agrees("project.analysis_runs.list", "result", {"runs": [run], "next_offset": None}, False)


@pytest.mark.parametrize("changes", [
    {"expected_revision": True}, {"expected_revision": -1}, {"expected_revision": 2**63},
    {"run_id": "not-a-uuid"}, {"run_id": None}, {"snapshot_id": 4}, {"handle": "old-handle"},
    {"bindings": {}}, {"bindings": []}, {"bindings": {"data": {}}},
    {"bindings": {"data": {"file": None}}}, {"bindings": {"bad/name": {"file": IDENTITY}}},
    {"bindings": {"Data": {"file": IDENTITY}}}, {"bindings": {"_data": {"file": IDENTITY}}},
    {"bindings": {"data-files": {"file": IDENTITY}}},
    {"bindings": {"data": {"": IDENTITY}}},
    {"bindings": {"data": {str(i): IDENTITY for i in range(101)}}},
    {"bindings": {f"binding_{i}": {"file": IDENTITY} for i in range(33)}},
    {"execute": True}, {"mode": "remote"}, {"profile": "phone"},
])
def test_preparation_rejects_unbounded_or_implicit_execution_parameters(changes):
    params = {**preparation(), **changes}
    assert validate_params("project.analysis_runs.prepare", params)
    agrees("project.analysis_runs.prepare", "params", params, False)


@pytest.mark.parametrize("path,value", [
    (("status",), "retrying"), (("source_revision",), True), (("profile",), "web"),
    (("budget", "max_seconds"), 301), (("budget", "max_output_bytes"), 2**31),
    (("bindings", "data", "fields/signed.dat", "size"), -1),
    (("bindings", "data", "fields/signed.dat", "sha256"), "sha256:" + DIGEST),
    (("plan_sha256",), "c" * 63), (("executor_id",), "process-1"),
    (("error",), {"code": "failed", "message": ""}),
    (("document", "outputs"), None), (("document", "graph", "outputs"), {}),
])
def test_run_contract_rejects_bad_identity_types_and_incomplete_definitions(path, value):
    run = prepared_run()
    target = run
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    agrees("project.analysis_runs.get", "result", {"run": run}, False)


def test_partial_failure_can_have_an_archived_result_without_becoming_successful():
    run = prepared_run()
    run["document"]["outputs"] = ["data"]
    run.update(status="failed", started_at=run["created_at"], finished_at=run["created_at"],
               executor_id=IDENTITY, error={"code": "graph_errors", "message": "One output failed"},
               result={"directory": f".stk/analysis-runs/{IDENTITY}/result", "manifest_sha256": DIGEST,
                       "graph_hash": DIGEST, "output_count": 1, "has_payload": True,
                       "has_errors": True, "size_bytes": 256})
    result = {"run": run, "result": {"schema": "stk.graph-result/1", "outputs": {},
              "errors": [{"node": "image", "message": "Unavailable output"}]}, "blob_dir": "/verified/archive/blobs"}
    agrees("project.analysis_runs.result", "result", result, True)
    assert result["run"]["status"] == "failed"
    empty_archive = deepcopy(result)
    empty_archive["run"]["result"]["size_bytes"] = 0
    agrees("project.analysis_runs.result", "result", empty_archive, False)
    for bad in ({**result, "blob_dir": ""}, {"result": result["result"], "blob_dir": result["blob_dir"]}):
        agrees("project.analysis_runs.result", "result", bad, False)


@pytest.mark.parametrize("params", [{"handle": HANDLE, "limit": 0}, {"handle": HANDLE, "limit": 101},
                                    {"handle": HANDLE, "offset": True}, {"handle": HANDLE, "offset": -1},
                                    {"handle": HANDLE, "recover": True}])
def test_list_has_bounded_read_only_parameters(params):
    agrees("project.analysis_runs.list", "params", params, False)
