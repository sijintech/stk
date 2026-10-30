"""Failure evidence and independent scientific output checks for the site demo."""

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def demo():
    path = Path(__file__).resolve().parents[1] / "examples/runtime/run_demo.py"
    spec = importlib.util.spec_from_file_location("stk_acceptance_demo", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_acceptance_connection_failure_keeps_report(demo, tmp_path, monkeypatch):
    monkeypatch.delenv("STK_RUNTIME_URL", raising=False)
    result = demo.main(
        [
            "--state-dir",
            str(tmp_path / "missing"),
            "--output",
            str(tmp_path / "results"),
        ]
    )
    assert result == 1
    report = json.loads(
        next((tmp_path / "results").glob("acceptance-*.json")).read_text()
    )
    assert report["status"] == "failed" and not report["verified"]
    assert report["tasks"] == []
    assert report["source_sha256"] and report["finished_at"]


def test_acceptance_lost_submit_response_saves_retry_contract(
    demo, tmp_path, monkeypatch
):
    class LostResponseClient:
        url = "http://127.0.0.1:9876"
        token = "private-acceptance-token"

        def health(self):
            return {"api_version": 1, "status": "ok"}

        def create_workspace(self, name):
            return {"id": "b" * 32}

        def upload(self, *args):
            pass

        def submit(self, spec, key):
            # The retry contract must already be on disk before the request.
            report = json.loads(next(tmp_path.glob("acceptance-*.json")).read_text())
            assert report["tasks"][0]["spec"] == spec.to_dict()
            assert report["tasks"][0]["idempotency_key"] == key
            raise ConnectionError("response lost " + self.token)

    monkeypatch.setattr(demo, "get_client", lambda *_: LostResponseClient())
    assert demo.main(["--output", str(tmp_path)]) == 1
    report = json.loads(next(tmp_path.glob("acceptance-*.json")).read_text())
    assert report["status"] == "failed" and not report["verified"]
    assert report["tasks"][0]["state"] == "submitting"
    assert "id" not in report["tasks"][0]
    assert LostResponseClient.token not in json.dumps(report)


def test_incorrect_field_is_rejected_even_when_summary_is_correct(demo, tmp_path):
    np = pytest.importorskip("numpy")
    from PIL import Image
    from toolkits.sviz.field import read_field, write_field

    # Test the independent verifier with known outputs. Starting the complete
    # simulator here couples this corruption check to cold plotting/font setup;
    # the shipped sweep and science tests exercise that producer separately.
    x, y, z = np.indices((8, 6, 4))
    field = (x + 2 * y + 3 * z).astype(float)
    write_field(tmp_path / "field.dat", field)
    write_field(tmp_path / "field.vtk", field)
    Image.new("RGB", (2, 2), (20, 80, 160)).save(tmp_path / "preview.png")
    (tmp_path / "summary.json").write_text(
        json.dumps({"amplitude": 1, "mean": 13, "minimum": 0, "maximum": 26})
    )
    assert (
        demo.verify_outputs(tmp_path, 1)["field_max_absolute_error"]["field.vtk"] == 0
    )
    original = read_field(tmp_path / "field.vtk")
    changed = original.copy()
    # Preserve every summary statistic, so only checking field values finds it.
    changed[1, 0, 0, 0] += 1
    changed[1, 0, 1, 0] -= 1
    for statistic in (np.mean, np.min, np.max):
        assert statistic(changed) == statistic(original)
    write_field(tmp_path / "field.vtk", changed)
    with pytest.raises(ValueError, match="field.vtk"):
        demo.verify_outputs(tmp_path, 1)
    write_field(tmp_path / "field.vtk", original)
    summary = json.loads((tmp_path / "summary.json").read_text())
    summary["mean"] = np.nan
    (tmp_path / "summary.json").write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="mean"):
        demo.verify_outputs(tmp_path, 1)
