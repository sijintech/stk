"""An older table cache must not bypass corrected input validation."""
from dataclasses import replace
import hashlib
import os

import pytest

from suan.data.model import Table
from suan.graph.cache import GraphCache
from suan.graph.catalog import default_registry
from suan.graph.evaluator import EvaluationFailed, evaluate
from suan.graph.registry import Registry
from suan.graph.resolve import LocalDirResolver
from suan.graph.service import MemoryBlobSink, evaluate_request


def test_old_ambiguous_table_cache_does_not_hide_duplicate_header_error(tmp_path):
    (tmp_path / "stress-strain.dat").write_text(
        "Strain Stress Stress\n0 0.125 1\n0.01 0.15 1.25\n0.02 0.175 1.5\n")
    live = default_registry()

    def legacy(ctx, inputs, params):
        # Seed the output older releases cached after retaining the last
        # Stress column. The genuine file fingerprint and graph are unchanged.
        return Table.from_columns({"Strain": [0, 0.01, 0.02], "Stress": [1, 1.25, 1.5]},
                                  units={"Strain": "1", "Stress": "GPa"})

    older = Registry([replace(node, impl_version=1, impl=legacy) if node.id == "stk.source.table@1" else node
                      for node in live])
    cache = GraphCache(tmp_path / "cache")
    resolver = LocalDirResolver({"data": tmp_path})
    request = {"preset": "lammps-modulus", "outputs": ["summary"]}
    arguments = {"resolver": resolver, "cache": cache, "cache_dir": tmp_path / "cache",
                 "blob_sink": MemoryBlobSink()}
    previous = evaluate_request(request, registry=older, **arguments)
    assert previous["outputs"]["summary"]["columns"]["Modulus"] == pytest.approx([25])
    assert evaluate_request(request, registry=older, **arguments)["cache"]["hits"] > 0
    with pytest.raises(EvaluationFailed, match="unique") as caught:
        evaluate_request(request, registry=live, **arguments)
    assert "summary" not in caught.value.partial.outputs


def evaluate_csv(root, cache, *, wrapped, **options):
    graph = {"schema": "stk.graph/1", "catalog": {"stk": 1}, "nodes": [
        {"id": "table", "type": "stk.source.table@1", "params": {"binding": "data", "path": "values.csv"}}],
        "outputs": {"table": "table.out"}}
    resolver = LocalDirResolver({"data": root})
    if wrapped:
        source = resolver.resolve("data")

        class CustomFileSource:
            def __getattr__(self, name):
                return getattr(source, name)

        resolver = {"data": CustomFileSource()}
    return evaluate(graph, registry=default_registry(), resolver=resolver, cache=cache, **options)


@pytest.mark.parametrize("after_planning", [False, True])
@pytest.mark.parametrize("wrapped", [False, True])
def test_table_cache_is_bound_to_actual_bytes_even_with_restored_mtime(tmp_path, after_planning, wrapped):
    path = tmp_path / "values.csv"
    original, changed = b"step,value\n1,2\n", b"step,value\n1,9\n"
    path.write_bytes(original)
    stamp = path.stat()
    cache = GraphCache()

    def write(data):
        path.write_bytes(data)
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))

    if after_planning:
        def edit(event):
            if event["type"] == "node.started":
                write(changed)

        with pytest.raises(EvaluationFailed) as error:
            evaluate_csv(tmp_path, cache, wrapped=wrapped, on_event=edit)
        assert error.value.errors[0]["code"] == "invalid_data"
        write(original)
        expected, value = original, 2
    else:
        assert evaluate_csv(tmp_path, cache, wrapped=wrapped).outputs["table"].column("value").tolist() == [2]
        write(changed)
        expected, value = changed, 9

    result = evaluate_csv(tmp_path, cache, wrapped=wrapped)
    table = result.outputs["table"]
    assert result.evaluated == ["table"] and table.column("value").tolist() == [value]
    assert table.provenance.used[0]["sha256"] == hashlib.sha256(expected).hexdigest()
    assert evaluate_csv(tmp_path, cache, wrapped=wrapped).evaluated == []
