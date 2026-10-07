"""The offline example project: one walk through parameters, outputs, results and an analysis run."""
import json
import subprocess
import sys

import pytest

from suan.project import ProjectStore
from suan.scripting.headless import connect
from suan.workflows.demo import TEMPERATURES, create_demo
from test_desktop_bridge import ROOT, bridge_env, inproc  # noqa: F401


def _vtk_reader_available():
    try:
        import vtkmodules  # noqa: F401
    except ImportError:
        return False
    return True


def test_example_project_walks_the_main_path_offline(bridge_env, tmp_path):
    with connect(tmp_path / "state") as stk:
        made = create_demo(stk, tmp_path / "example")
    store = ProjectStore(tmp_path / "example")
    tables = {table["id"]: table for table in store.snapshot()["tables"]}
    cases, results = tables[made["cases_table"]], tables[made["results_table"]]
    temperatures = [next(v for v in row["values"].values() if isinstance(v, (int, float))) for row in cases["records"]]
    assert temperatures == list(TEMPERATURES)
    assert len(results["records"]) == 3
    assert all(any(d["kind"] == "reference" for d in row["definitions"].values()) for row in results["records"])
    for i, temperature in enumerate(TEMPERATURES):
        metrics = json.loads((tmp_path / "example" / "results" / "demo" / f"case-{i + 1}" / "metrics.json").read_text())
        assert metrics["synthetic"] and metrics["max_K"] == pytest.approx(temperature)  # The grid centre peaks at T.
    assert (tmp_path / "example" / "README.md").exists()
    workflow = store.workflows.get(made["workflow_id"])["workflow"]
    assert workflow["state"] == "readable" and [s["id"] for s in workflow["document"]["steps"]] == ["cases", "fields", "temperature"]
    checked = store.workflows.validate(workflow["document"])
    assert checked["ok"], checked["issues"]
    assert [s["name"] for s in checked["steps"]] == ["Cases / 算例", None, "Temperature field / 温度场"]
    expected = "succeeded" if _vtk_reader_available() else made["run_status"]
    assert made["run_status"] == expected, made
    with pytest.raises(ValueError, match="empty folder"):
        with connect(tmp_path / "state") as stk:
            create_demo(stk, tmp_path / "example")


def test_suan_demo_command_prints_the_project(bridge_env, tmp_path):
    result = subprocess.run([sys.executable, "-m", "suan.cli.main", "demo", str(tmp_path / "cli-example"),
                             "--state-dir", str(tmp_path / "state")], capture_output=True, text=True, cwd=str(ROOT), timeout=300)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["directory"] == str(tmp_path / "cli-example")


def test_bridge_builds_the_example_for_the_desktop(inproc, tmp_path):
    harness = inproc()
    made = harness.call("demo.create", {"directory": str(tmp_path / "desktop-example")}, timeout=300)
    assert made["directory"] == str(tmp_path / "desktop-example") and made["run_id"]
    assert harness.call("project.open", {"directory": made["directory"]})["project"]["id"] == made["project_id"]
    error = harness.error("demo.create", {"directory": made["directory"]})
    assert error["code"] == "invalid_params" and "empty folder" in error["message"]
    assert not harness.violations
    harness.close()
