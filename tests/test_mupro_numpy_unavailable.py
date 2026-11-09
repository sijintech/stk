"""MuFerro DAT frames, tables and the run index report ``unavailable`` without NumPy, before reading data."""
import sys

import pytest

pytest.importorskip("numpy")

from mupro_fake import write_case, write_outputs  # noqa: E402
from suan.connectors.api import ConnectorError  # noqa: E402
from suan.connectors.files import LocalFiles  # noqa: E402
from suan.connectors.mupro import MuFerroConnector  # noqa: E402
from suan.connectors.mupro.tables import ENERGY_COLUMNS  # noqa: E402
from suan.data.manifest import validate_result  # noqa: E402
from suan.graph.catalog import build_registry  # noqa: E402
from suan.graph.evaluator import EvaluationFailed, evaluate  # noqa: E402
from suan.graph.resolve import LocalDirResolver  # noqa: E402


def run_graph():
    return {"schema": "stk.graph/1", "catalog": {"stk": 1}, "nodes": [
        {"id": "run", "type": "stk.source.muferro_run@1", "params": {"binding": "run"}}],
        "outputs": {"result": "run.result", "frames": "run.frames"}}


@pytest.fixture
def opened(monkeypatch):
    paths = []
    open_source = LocalFiles.open

    def record_open(source, path):
        paths.append(path)
        return open_source(source, path)

    monkeypatch.setattr(LocalFiles, "open", record_open)
    return paths


def test_metadata_describe_without_numpy_does_not_read_tables_or_frames(tmp_path, monkeypatch, opened):
    write_case(tmp_path)
    write_outputs(tmp_path)
    source = LocalFiles(tmp_path)
    available = MuFerroConnector().describe(source)
    opened.clear()
    with monkeypatch.context() as missing:
        missing.setitem(sys.modules, "numpy", None)
        absent = MuFerroConnector().describe(source)
    assert validate_result(absent) == []
    assert [d["id"] for d in absent["datasets"]] == [d["id"] for d in available["datasets"]]
    assert {"Polar", "energy", "progress"} <= {d["id"] for d in absent["datasets"]}
    energy = next(d for d in absent["datasets"] if d["id"] == "energy")
    assert [c["name"] for c in energy["columns"]] == ["step", *ENERGY_COLUMNS]
    assert energy["geometry"]["rows"] is None
    assert next(d for d in available["datasets"] if d["id"] == "energy")["geometry"]["rows"] > 0
    assert available["qoi"] and absent["qoi"] == []
    for key in ("state", "complete", "verification", "files"):
        assert absent[key] == available[key]
    # Only the case TOML is read; energy, progress and DAT frame bytes are not opened.
    assert all(path.endswith(".toml") for path in opened), opened


def test_frame_and_table_reads_without_numpy_are_unavailable_before_opening(tmp_path, monkeypatch, opened):
    write_case(tmp_path)
    write_outputs(tmp_path)
    source = LocalFiles(tmp_path)
    connector = MuFerroConnector()
    result = connector.describe(source)
    opened.clear()
    with monkeypatch.context() as missing:
        missing.setitem(sys.modules, "numpy", None)
        handles = {name: connector.open(source, name, result=result) for name in ("Polar", "energy", "progress")}
        for operation in (lambda: handles["Polar"].read(frame={"latest": True}),
                          lambda: handles["Polar"].stats(frame={"latest": True}),
                          lambda: handles["energy"].read(),
                          lambda: handles["energy"].stats(field="Total Energy"),
                          lambda: handles["progress"].read()):
            with pytest.raises(ConnectorError) as error:
                operation()
            assert error.value.code == "unavailable"
        assert opened == []
        # Supported request errors keep their codes.
        for operation, code in ((lambda: connector.open(source, "Missing", result=result), "not_found"),
                                (lambda: handles["Polar"].read(fields=["Other"]), "invalid_param"),
                                (lambda: handles["Polar"].read(frame={"step": 1, "policy": "exact"}),
                                 "frame_not_found")):
            with pytest.raises(ConnectorError) as error:
                operation()
            assert error.value.code == code
        assert opened == []
    image = handles["Polar"].read(frame={"latest": True})
    assert image.time.step == 2 and image.field("Polar").components == 3


def test_run_index_without_numpy_fails_during_planning(tmp_path, monkeypatch, opened):
    write_case(tmp_path)
    write_outputs(tmp_path)
    registry = build_registry(entry_points=False)
    events = []
    with monkeypatch.context() as missing:
        missing.setitem(sys.modules, "numpy", None)
        with pytest.raises(EvaluationFailed) as failure:
            evaluate(run_graph(), registry=registry, resolver=LocalDirResolver({"run": tmp_path}),
                     on_event=lambda event: events.append(event["type"]))
        with pytest.raises(EvaluationFailed) as unbound:
            evaluate(run_graph(), registry=registry, resolver=LocalDirResolver({}))
        assert [error["code"] for error in unbound.value.errors] == ["unknown_binding"]
    assert [error["code"] for error in failure.value.errors] == ["unavailable"]
    assert "node.started" not in events and "node.failed" in events
    assert opened == []
    result = evaluate(run_graph(), registry=registry, resolver=LocalDirResolver({"run": tmp_path}))
    assert result.outputs["frames"].n_rows > 0 and result.outputs["result"]["qoi"]
