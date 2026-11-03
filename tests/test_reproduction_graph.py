"""Real Registry/evaluator/Table-source comparison; no papers or solvers."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

np = pytest.importorskip("numpy")

from suan.data.model import Provenance, Table
from suan.graph.cache import GraphCache
from suan.graph.catalog import build_registry, compare_catalog
from suan.graph.evaluator import EvaluationFailed, evaluate
from suan.graph.nodes import reproduction
from suan.graph.registry import Cancelled, NodeExecutionError
from suan.graph.resolve import LocalDirResolver
from suan.graph.schema import GraphValidationError
from suan.reproduction import verify

ROOT = Path(__file__).parents[1]


def parameters(kind="curve", **changes):
    result = {"kind": kind, "reference_value": "value", "actual_value": "value",
              "reference_status": "succeeded", "actual_status": "succeeded", "absolute": 0, "relative": 0,
              "alignment": "exact"}
    if kind == "curve": result.update(reference_x="x", actual_x="x", domain=[0, 2])
    return {**result, **changes}


def graph(params=None, *, units=None, plot=False):
    units = units or {"reference": {"x": "s", "value": "m"}, "actual": {"x": "s", "value": "m"}}
    nodes = [{"id": side, "type": "stk.source.table@1", "params": {
        "binding": "input", "path": side+".csv", "format": "csv", "units": units[side]}}
        for side in ("reference", "actual")]
    nodes.append({"id": "compare", "type": "stk.analysis.reproduction_compare@1",
                  "inputs": {side: {"from": side+".out"} for side in ("reference", "actual")},
                  "params": params or parameters()})
    outputs = {"comparison": "compare.comparison", "errors": "compare.errors"}
    if plot:
        nodes.append({"id": "plot", "type": "stk.plot.line@1", "inputs": {"table": {"from": "compare.errors"}},
                      "params": {"x": "x", "y": ["absolute_error", "allowed_error"]}})
        outputs["plot"] = "plot.plot"
    return {"schema": "stk.graph/1", "catalog": {"stk": 1}, "nodes": nodes, "outputs": outputs}


def run(tmp_path, *, reference="x,value\n0,0\n1,2\n2,4\n", actual="x,value\n0,0\n1,2\n2,4\n", params=None, units=None, plot=False, cache=None):
    folder = tmp_path/"input"; folder.mkdir(exist_ok=True)
    for name, text in (("reference", reference), ("actual", actual)):
        (folder/(name+".csv")).write_text(text)
    return evaluate(graph(params, units=units, plot=plot), registry=build_registry(entry_points=False),
                    resolver=LocalDirResolver({"input": folder}), cache=cache or GraphCache())


def test_actual_source_registry_evaluator_and_plot_match_independent_errors(tmp_path):
    result = run(tmp_path, reference="x,value\n0,0\n1,1\n2,2\n", actual="x,value\n0,1\n1,-1\n2,5\n",
                 params=parameters(absolute=2), plot=True)
    document, errors = result.outputs["comparison"], result.outputs["errors"]
    assert verify(document) and document["result"]["status"] == "failed"
    assert document["result"]["metrics"]["rmse"] == pytest.approx(np.sqrt(14/3))
    assert errors.column("signed_error").tolist() == [1, -2, 3]
    assert errors.column("status").tolist() == ["passed", "passed", "failed"]
    assert errors.field("absolute_error").unit == "m"
    assert errors.field("reference_index").dtype == "int64"
    assert result.output_types == {"comparison": "value", "errors": "table", "plot": "plot"}
    assert result.outputs["plot"]["schema"] == "stk.plot/1"
    source = document["plan"]["reference"]["source"]
    assert source["authority"] == "unverified" and source["table_id"] == "reference"
    assert source["columns"]["value"]["values"] == [0, 1, 2]
    assert source["columns"]["value"]["descriptor"]["dtype"] == "int64"
    assert source["provenance"]["used"][0]["sha256"] == hashlib.sha256((tmp_path/"input/reference.csv").read_bytes()).hexdigest()


def test_explicit_linear_alignment_and_exact_interpolation_inputs_are_preserved(tmp_path):
    result = run(tmp_path, reference="x,value\n0,0\n1,1\n3,3\n", actual="x,value\n0,0\n3,3\n",
                 params=parameters(alignment="linear", domain=[0,3]))
    document, table = result.outputs["comparison"], result.outputs["errors"]
    assert document["result"]["status"] == "passed"
    assert table.column("actual").tolist() == [0,1,3]
    exact = json.loads(table.column("actual_exact")[1])
    assert exact["alignment"] == "linear" and exact["reference_x"] == 1
    assert [p["x"] for p in exact["points"]] == [0,3]
    assert not table.field("actual").lossy


def test_float_display_columns_mark_actual_precision_loss_and_keep_original_ints(tmp_path):
    large = 9007199254740993
    result = run(tmp_path, reference=f"value\n{large}\n", actual=f"value\n{large}\n", params=parameters("scalar"),
                 units={"reference":{"value":"1"},"actual":{"value":"1"}})
    document, table = result.outputs["comparison"], result.outputs["errors"]
    assert document["result"]["status"] == "passed"
    assert document["plan"]["actual"]["value"] == large
    assert table.field("reference").lossy and table.field("actual").lossy
    assert json.loads(table.column("reference_exact")[0]) == large
    assert json.loads(table.column("actual_exact")[0]) == large


def test_interpolation_rounding_is_marked_without_changing_numeric_comparison(tmp_path):
    result = run(tmp_path, reference="x,value\n0,0\n1,0.3333333333333333\n3,1\n", actual="x,value\n0,0\n3,1\n",
                 params=parameters(alignment="linear", domain=[0,3], absolute=1e-15))
    assert result.outputs["comparison"]["result"]["status"] == "passed"
    assert result.outputs["errors"].field("actual").lossy


@pytest.mark.parametrize("unit,reason", [("unspecified", "unit_unknown"),("cm", "unit_mismatch"),("normalized", "unit_unknown")])
def test_actual_table_units_do_not_get_overridden_or_inferred(tmp_path, unit, reason):
    result = run(tmp_path, units={"reference":{"x":"s","value":"m"},"actual":{"x":"s","value":unit}})
    assert result.outputs["comparison"]["result"]["status"] == "indeterminate"
    assert reason in result.outputs["comparison"]["result"]["reasons"]
    assert result.outputs["errors"].field("actual").unit == unit


def test_explicit_failed_run_cannot_pass_even_with_equal_values(tmp_path):
    result = run(tmp_path, params=parameters(actual_status="failed"))
    assert result.outputs["comparison"]["result"]["status"] == "indeterminate"
    assert "actual_run_failed" in result.outputs["comparison"]["result"]["reasons"]
    assert result.outputs["errors"].column("status").tolist() == ["indeterminate"]*3


def test_explicit_missing_scalar_source_can_be_empty_without_inventing_a_value(tmp_path):
    result=run(tmp_path,reference="value\n10\n",actual="value\n",params=parameters("scalar",actual_status="missing"),
               units={"reference":{"value":"K"},"actual":{"value":"K"}})
    document=result.outputs["comparison"]
    assert document["result"]["status"]=="indeterminate" and document["plan"]["actual"]["value"] is None
    assert document["plan"]["actual"]["source"]["columns"]["value"]["values"]==[]


def test_missing_and_failed_rows_are_retained_in_frozen_original_columns(tmp_path):
    result = run(tmp_path, actual="x,value,state\n0,0,ok\n1,,missing\n2,4,failed\n",
                 params=parameters(actual_row_status="state"))
    document, table = result.outputs["comparison"], result.outputs["errors"]
    assert document["result"]["status"] == "indeterminate"
    assert document["plan"]["actual"]["source"]["columns"]["value"]["values"] == [0.0,"NaN",4.0]
    assert document["plan"]["actual"]["source"]["columns"]["state"]["values"] == ["ok","missing","failed"]
    assert table.n_rows == 3 and table.column("status").tolist() == ["passed","indeterminate","indeterminate"]
    assert np.isnan(table.column("absolute_error")[1:]).all()


def test_missing_position_cannot_be_interpolated_over(tmp_path):
    result = run(tmp_path, actual="x,value,state\n0,0,ok\n,,missing\n2,4,ok\n", params=parameters(alignment="linear",actual_row_status="state"))
    assert result.outputs["comparison"]["result"]["status"] == "indeterminate"
    assert result.outputs["errors"].column("reason")[1] == "actual_segment_unavailable"


def test_partial_domain_does_not_become_a_successful_reproduction(tmp_path):
    result = run(tmp_path, actual="x,value\n1,2\n2,4\n", params=parameters(alignment="linear"))
    outcome = result.outputs["comparison"]["result"]
    assert outcome["status"] == "indeterminate" and outcome["metrics"]["compared_samples"] == 2
    assert "actual_domain_incomplete" in outcome["reasons"]


@pytest.mark.parametrize("missing", ["kind","reference_value","actual_value","reference_status","actual_status","absolute","relative","alignment"])
def test_required_choices_are_not_guessed_by_graph_validation(tmp_path, missing):
    params=parameters();params.pop(missing)
    with pytest.raises(GraphValidationError): run(tmp_path,params=params)


@pytest.mark.parametrize("params,actual", [
    (parameters(reference_value="absent"),"x,value\n0,0\n1,2\n2,4\n"),
    (parameters(domain=None),"x,value\n0,0\n1,2\n2,4\n"),
    (parameters(),"x,value\n1,2\n0,0\n2,4\n"),
    (parameters(),"x,value\n0,0\n0,2\n2,4\n"),
    (parameters(),"x,value\n0,0\n1,inf\n2,4\n"),
    (parameters(actual_row_status="value"),"x,value\n0,0\n1,2\n2,4\n"),
    (parameters(actual_row_status="state"),"x,value,state\n0,0,ok\n1,2,approved\n2,4,ok\n"),
    (parameters("scalar"),"x,value\n0,0\n1,2\n2,4\n"),
    (parameters("scalar",alignment="linear"),"x,value\n0,0\n1,2\n2,4\n"),
])
def test_bad_selection_order_infinity_status_or_scalar_shape_is_a_node_error(tmp_path, params, actual):
    with pytest.raises(EvaluationFailed): run(tmp_path,params=params,actual=actual)


def test_disk_cache_reopen_preserves_full_frozen_document_and_typed_errors(tmp_path):
    cache_root=tmp_path/"cache";first=run(tmp_path,cache=GraphCache(cache_root))
    second=run(tmp_path,cache=GraphCache(cache_root))
    assert second.outputs["comparison"] == first.outputs["comparison"] and verify(second.outputs["comparison"])
    assert "compare" not in second.evaluated and second.cache["hits"] > 0
    assert second.outputs["errors"].column("actual_exact").tolist() == first.outputs["errors"].column("actual_exact").tolist()
    third=run(tmp_path,cache=GraphCache(cache_root),actual="x,value\n0,0\n1,3\n2,4\n")
    assert third.outputs["comparison"]["result"]["status"] == "failed" and "compare" in third.evaluated
    assert third.outputs["comparison"]["plan_sha256"] != first.outputs["comparison"]["plan_sha256"]


class Context:
    def __init__(self):self.checks=0
    def check(self):self.checks+=1


def direct(table, params=None, *, context=None):
    node=reproduction.reproduction_compare.stk_node_type
    return reproduction.reproduction_compare(context or Context(),{"reference":table,"actual":table},node.normalize_params(params or parameters()))


@pytest.mark.parametrize("metadata", [object(), {"deep": [[[[[[[[[[[[[[1]]]]]]]]]]]]]]}, {"large":"a"*(2*1024*1024+1)}])
def test_unrepresentable_metadata_is_not_silently_removed(metadata):
    table=Table.from_columns({"x":np.array([0.,1.,2.]),"value":np.array([0.,2.,4.])},units={"x":"s","value":"m"})
    table.attrs["evidence"]=metadata
    with pytest.raises(NodeExecutionError) as caught: direct(table)
    assert caught.value.code == "invalid_result" and "evidence" not in str(caught.value)


def test_provenance_iterables_are_rejected_before_any_implicit_iteration():
    class UnexpectedIterator:
        def __iter__(self): raise AssertionError("Unsupported provenance was iterated")
    table=Table.from_columns({"x":np.array([0.,1.,2.]),"value":np.array([0.,2.,4.])},units={"x":"s","value":"m"},
                             provenance=Provenance(used=UnexpectedIterator()))
    with pytest.raises(NodeExecutionError) as caught: direct(table)
    assert caught.value.code=="invalid_result"


def test_original_table_metadata_and_columns_are_detached_and_never_mutated():
    table=Table.from_columns({"x":np.array([0.,1.,2.]),"value":np.array([0.,2.,4.])},units={"x":"s","value":"m"},
                             provenance=Provenance(agent={"reader":"self-authored"}),attrs={"assumption":"not reviewed"})
    before=table.column("value").copy();document=direct(table)["comparison"]
    table.attrs["assumption"]="changed"
    assert np.array_equal(table.column("value"),before)
    assert document["plan"]["actual"]["source"]["attrs"]["assumption"] == "not reviewed"
    assert verify(document)


def test_mutated_field_dtype_cannot_be_frozen_as_false_original_dtype():
    from dataclasses import replace
    table=Table.from_columns({"x":np.array([0.,1.,2.]),"value":np.array([0.,2.,4.])},units={"x":"s","value":"m"})
    table.fields["value"]=replace(table.field("value"),dtype="int64")
    with pytest.raises(NodeExecutionError) as caught: direct(table)
    assert caught.value.code=="invalid_result"


def test_known_upstream_precision_loss_remains_visible_in_derived_columns():
    from dataclasses import replace
    table=Table.from_columns({"x":np.array([0.,1.,2.]),"value":np.array([0.,2.,4.])},units={"x":"s","value":"m"})
    table.fields["value"]=replace(table.field("value"),lossy=True)
    result=direct(table)
    assert result["comparison"]["result"]["status"]=="passed"
    assert result["errors"].field("reference").lossy
    assert result["errors"].field("actual").lossy
    assert result["errors"].field("absolute_error").lossy


def test_large_table_limit_is_enforced_before_conversion_and_can_cancel():
    table=Table.from_columns({"x":np.arange(4097),"value":np.arange(4097)},units={"x":"s","value":"m"})
    with pytest.raises(NodeExecutionError) as caught: direct(table)
    assert caught.value.code == "budget_exceeded"
    class Stop(Context):
        def check(self): raise Cancelled("cancelled")
    small=Table.from_columns({"x":np.arange(3),"value":np.arange(3)},units={"x":"s","value":"m"})
    with pytest.raises(Cancelled): direct(small,context=Stop())


def test_full_supported_table_size_traverses_sources_and_evaluator(tmp_path):
    csv = "x,value\n" + "".join(f"{i},{2*i}\n" for i in range(4096))
    result = run(tmp_path, reference=csv, actual=csv, params=parameters(domain=[0,4095]))
    assert result.outputs["comparison"]["result"]["status"] == "passed"
    assert result.outputs["errors"].n_rows == 4096
    assert result.outputs["comparison"]["result"]["metrics"]["compared_samples"] == 4096
    assert verify(result.outputs["comparison"])


def test_new_catalog_declaration_is_equal_and_imports_without_numpy(tmp_path):
    declared=runpy.run_path(str(ROOT/"docs/specs/catalog/m1_nodes.py"))["catalog"]()
    assert compare_catalog(build_registry(entry_points=False).catalog(),declared) == []
    entry=next(n for n in declared["nodes"] if n["id"]=="stk.analysis.reproduction_compare@1")
    assert entry["impl_version"]==1 and entry["cache"]=="disk"
    script='''import sys,builtins
sys.dont_write_bytecode=True
sys.path.insert(0,sys.argv[1]);original=builtins.__import__
def guarded(name,*a,**kw):
 if name.split('.')[0] in {'numpy','vtk','torch','transformers'}:raise AssertionError(name)
 return original(name,*a,**kw)
builtins.__import__=guarded
from suan.graph.nodes import reproduction
assert reproduction.reproduction_compare.stk_node_type.id == 'stk.analysis.reproduction_compare@1'
'''
    child=subprocess.run([sys.executable,'-I','-c',script,str(ROOT)],capture_output=True,text=True,timeout=10)
    assert child.returncode==0,child.stderr
