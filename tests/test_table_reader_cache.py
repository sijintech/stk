"""An older table cache must not bypass corrected input validation."""
from dataclasses import replace

import pytest

from suan.data.model import Table
from suan.graph.cache import GraphCache
from suan.graph.catalog import default_registry
from suan.graph.evaluator import EvaluationFailed
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
