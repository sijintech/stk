"""Raw multi-log provenance survives fitting and graph result serialization."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from suan.graph.nodes import pet_study_sources
from suan.graph.registry import NodeExecutionError
from suan.graph.resolve import LocalDirResolver
from suan.lammps.analysis import tg


def log(temperature):
    density = 1.4 - .0002 * (temperature - 250) - .0005 * max(0, temperature - 340)
    return (f"LAMMPS (test fixture)\nunits real\nrun 3\nPer MPI rank memory allocation (min/avg/max) = 1 | 1 | 1 Mbytes\nStep Temp Press Density PotEng\n"
            + "".join(f"{step} {temperature} 1 {density:.15g} -1\n" for step in range(4))
            + "Loop time of 1 on 1 procs for 3 steps with 1 atoms\nTotal wall time: 0:00:01\n")


@pytest.fixture
def series(tmp_path):
    paths, entries = [], []
    for index, temperature in enumerate((250, 275, 300, 325, 350, 375, 400, 425)):
        path = f"tg-{index}.log"
        raw = log(temperature).replace("\n", "\r\n").encode("utf-8")
        (tmp_path / path).write_bytes(raw)
        paths.append(path)
        entries.append({"path": path, "sha256": hashlib.sha256(raw).hexdigest(), "simulation_run_id": "fixture"})
    receipt = {"format": "stk.pet-density-series/1", "logs": entries}
    (tmp_path / "tg-series.json").write_text(json.dumps(receipt), encoding="utf-8")
    resolver = LocalDirResolver({"data": tmp_path})
    context = SimpleNamespace(resolve=resolver.resolve, check=lambda: None, node_id="series")
    return tmp_path, context, {"binding": "data", "paths": paths, "receipt_path": "tg-series.json"}


def test_every_original_byte_digest_and_receipt_survive_the_fit(series):
    folder, context, parameters = series
    table = pet_study_sources.density_source(context, {}, parameters)
    result = tg(table)
    assert result["summary"].column("Tg")[0] == pytest.approx(340)
    expected = [{"path": path, "sha256": hashlib.sha256((folder / path).read_bytes()).hexdigest(), "role": "input"}
                for path in [*parameters["paths"], parameters["receipt_path"]]]
    assert result["diagnostics"]["source"]["used"] == expected
    assert table.attrs["study_receipt"]["logs"][0]["simulation_run_id"] == "fixture"
    before = pet_study_sources.fingerprint(context, {}, parameters)
    (folder / parameters["paths"][0]).write_bytes(log(250).encode("utf-8"))
    after = pet_study_sources.fingerprint(context, {}, parameters)
    assert before != after
    with pytest.raises(NodeExecutionError, match="does not match"):
        pet_study_sources.density_source(context, {}, parameters)


@pytest.mark.parametrize("paths", [[], ["same", "same"], ["../escape"], ["/escape"], ["x\\y"], ["x"] * 99])
def test_invalid_members_and_paths_fail_before_source_reads(series, paths):
    _, context, parameters = series
    parameters["paths"] = paths
    context.resolve = lambda _: pytest.fail("invalid paths must not resolve a source")
    with pytest.raises(NodeExecutionError):
        pet_study_sources.density_source(context, {}, parameters)


def test_incomplete_or_wrong_receipt_and_failed_logs_are_not_accepted(series):
    folder, context, parameters = series
    receipt = json.loads((folder / "tg-series.json").read_text())
    receipt["logs"].pop()
    (folder / "tg-series.json").write_text(json.dumps(receipt))
    with pytest.raises(NodeExecutionError, match="incomplete"):
        pet_study_sources.density_source(context, {}, parameters)
    parameters["receipt_path"] = None
    (folder / parameters["paths"][0]).write_text(log(250).replace("Total wall time: 0:00:01", "ERROR: deliberate fixture"))
    with pytest.raises(NodeExecutionError):
        pet_study_sources.density_source(context, {}, parameters)


def test_frozen_log_provenance_survives_graph_delivery(series, tmp_path):
    from suan.graph.catalog import build_registry
    from suan.graph.service import MemoryBlobSink, evaluate_request
    folder, _, parameters = series
    registry = build_registry(entry_points=False)
    registry.register(pet_study_sources, replace=True)
    graph = {"schema": "stk.graph/1", "catalog": {"stk": 1}, "parameters": [], "nodes": [
        {"id": "series", "type": "stk.source.lammps_density_series@1", "params": parameters},
        {"id": "fit", "type": "stk.analysis.lammps_tg@1", "inputs": {"in": {"from": "series.out"}}}],
        "outputs": {"summary": "fit.summary", "diagnostics": "fit.diagnostics"}}
    result = evaluate_request({"graph": graph, "outputs": ["summary", "diagnostics"]},
        resolver=LocalDirResolver({"data": folder}), cache_dir=tmp_path / "cache", blob_sink=MemoryBlobSink(), registry=registry)
    assert not result.get("errors"), result
    used = result["outputs"]["diagnostics"]["value"]["source"]["used"]
    assert len(used) == 9
    assert used[0]["sha256"] == hashlib.sha256((folder / parameters["paths"][0]).read_bytes()).hexdigest()
