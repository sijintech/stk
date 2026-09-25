"""`suan graph` (catalog, schema, validate, run, doctor) and the built-in node catalog."""
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import types

import pytest
from click.testing import CliRunner

from suan.graph import catalog, nodes, service
from suan.graph.cli import _suffix, default_cache_dir, graph as graph_cli

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "specs" / "catalog" / "stk-catalog-m1.json"
M1_NODES = ROOT / "docs" / "specs" / "catalog" / "m1_nodes.py"


def invoke(*args):
    return CliRunner().invoke(graph_cli, [str(a) for a in args], catch_exceptions=False)


@pytest.fixture
def cli(tmp_path, monkeypatch):
    pytest.importorskip("numpy")
    from graph_testnodes import encode_scene, graph, make_registry, render_plot, write_run
    registry = make_registry()
    monkeypatch.setattr(catalog, "default_registry", lambda refresh=False: registry)
    monkeypatch.setattr(service, "_default_encode_scene", encode_scene)
    monkeypatch.setattr(service, "_default_render_plot", render_plot)
    graph_file = tmp_path / "pipeline.json"
    graph_file.write_text(json.dumps(graph()), encoding="utf-8")
    ns = types.SimpleNamespace(registry=registry, graph=graph, graph_file=graph_file,
                               run=write_run(tmp_path / "run"), out=tmp_path / "out", cache=tmp_path / "cache")
    return ns


def test_catalog_and_schema(cli):
    result = invoke("catalog", "--json")
    assert result.exit_code == 0
    document = json.loads(result.output)
    assert document["schema"] == "stk.catalog/1" and "test.source.frame@1" in [n["id"] for n in document["nodes"]]
    text = invoke("catalog").output
    assert "test.source.frame@1" in text and "source" in text
    schema = json.loads(invoke("schema").output)
    assert schema["$id"] == "urn:stk:schema:graph-1"


def test_validate(cli, tmp_path):
    result = invoke("validate", cli.graph_file)
    assert result.exit_code == 0 and result.output.startswith("ok: ")
    bad = cli.graph()
    bad["nodes"][2]["params"]["factor"] = "big"
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps(bad))
    result = invoke("validate", bad_file)
    assert result.exit_code == 1 and "error [invalid_param] /nodes/2/params/factor (scale)" in result.output
    result = invoke("validate", bad_file, "--json")
    assert result.exit_code == 1 and json.loads(result.output)["valid"] is False
    result = invoke("validate", cli.graph_file, "--param", "step=-1")
    assert result.exit_code == 1 and "invalid_parameter" in result.output
    assert invoke("validate", cli.graph_file, "--param", "step=100", "--param", "view=+x").exit_code == 0
    result = invoke("validate", tmp_path / "missing.json")
    assert result.exit_code == 1 and "No such graph file or preset" in result.output


def test_run_writes_every_output(cli):
    result = invoke("run", cli.graph_file, "--bind", f"run={cli.run}", "--out", cli.out, "--cache", cli.cache)
    assert result.exit_code == 0, result.output
    out = cli.out
    manifest = json.loads((out / "payload" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "stk.payload/2"
    for entry in manifest["buffers"]:
        assert (out / "payload" / f"{entry['sha256']}.bin").stat().st_size == entry["byteLength"]
    assert (out / "scene" / "manifest.json").is_file()
    assert (out / "image.png").read_bytes().startswith(b"\x89PNG")
    assert (out / "plot.png").read_bytes().startswith(b"\x89PNG")
    assert json.loads((out / "plot.data.json").read_text(encoding="utf-8"))["t"]["columns"]["stat"] == ["min", "max", "mean"]
    assert json.loads((out / "stats.json").read_text(encoding="utf-8"))["columns"]["stat"] == ["min", "max", "mean"]
    assert json.loads((out / "info.json").read_text(encoding="utf-8"))["step"] == 200
    document = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert document["schema"] == "stk.graph-result/1" and document["files"]["image"] == "image.png"
    assert "cache: 0 hits, 12 misses" in result.output
    again = invoke("run", cli.graph_file, "--bind", f"run={cli.run}", "--out", cli.out, "--cache", cli.cache,
                   "--output", "stats", "--json")
    assert again.exit_code == 0
    assert json.loads(again.output)["evaluated"] == ["frames"]  # a new process: the disk entries are reused
    assert (cli.cache / "objects").is_dir() and (cli.cache / "hashes.sqlite").is_file()


def test_run_series_over_steps_and_choices(cli):
    result = invoke("run", cli.graph_file, "--bind", f"run={cli.run}", "--out", cli.out, "--no-cache",
                    "--param", "step=all", "--output", "image", "--output", "info")
    assert result.exit_code == 0, result.output
    series = json.loads((cli.out / "series.json").read_text(encoding="utf-8"))
    assert series["schema"] == "stk.series/1" and series["parameter"] == "step"
    assert [frame["step"] for frame in series["frames"]] == [0, 100, 200]
    assert series["frames"][0]["outputs"] == {"image": "image.00000000.png", "info": "info.00000000.json"}
    for step in (0, 100, 200):
        assert json.loads((cli.out / f"info.{step:08d}.json").read_text(encoding="utf-8"))["step"] == step
        assert (cli.out / f"result.{step:08d}.json").is_file()
    views = invoke("run", cli.graph_file, "--bind", f"run={cli.run}", "--out", cli.out / "views", "--no-cache",
                   "--param", "view=all", "--output", "image", "--json")
    assert views.exit_code == 0, views.output
    frames = json.loads(views.output)["frames"]
    assert [f["view"] for f in frames] == ["iso", "+x", "-x", "+z"]
    assert frames[1]["outputs"]["image"] == "image.%2Bx.png"
    assert (cli.out / "views" / "image.-x.png").is_file()


def test_run_errors(cli, tmp_path):
    result = invoke("run", cli.graph_file, "--out", cli.out, "--no-cache")
    assert result.exit_code == 1 and "unknown_binding" in result.output
    result = invoke("run", cli.graph_file, "--bind", f"run={tmp_path / 'missing'}", "--out", cli.out, "--no-cache")
    assert result.exit_code == 1 and "not found" in result.output
    result = invoke("run", cli.graph_file, "--bind", "run", "--out", cli.out, "--cache", cli.cache)
    assert result.exit_code == 2 and not cli.cache.exists()  # rejected before anything is created
    partial = cli.graph(scale={"mode": "fail"})
    partial_file = tmp_path / "partial.json"
    partial_file.write_text(json.dumps(partial))
    result = invoke("run", partial_file, "--bind", f"run={cli.run}", "--out", cli.out, "--no-cache")
    assert result.exit_code == 1 and "node_failed" in result.output
    assert json.loads((cli.out / "info.json").read_text(encoding="utf-8"))["step"] == 200  # independent outputs still written


def test_outputs_never_overwrite_the_result_documents(cli, tmp_path):
    document = cli.graph()
    document["outputs"] = {"result": "info.info", "series": "stats.out", "image": "image.image"}
    graph_file = tmp_path / "named.json"
    graph_file.write_text(json.dumps(document))
    result = invoke("run", graph_file, "--bind", f"run={cli.run}", "--out", cli.out, "--no-cache")
    assert result.exit_code == 0, result.output
    assert json.loads((cli.out / "result.json").read_text(encoding="utf-8"))["schema"] == "stk.graph-result/1"
    assert json.loads((cli.out / "result.output.json").read_text(encoding="utf-8"))["step"] == 200
    assert json.loads((cli.out / "series.output.json").read_text(encoding="utf-8"))["columns"]["stat"] == ["min", "max", "mean"]
    files = json.loads((cli.out / "result.json").read_text(encoding="utf-8"))["files"]
    assert files == {"result": "result.output.json", "series": "series.output.json", "image": "image.png"}
    series = invoke("run", graph_file, "--bind", f"run={cli.run}", "--out", tmp_path / "all", "--no-cache",
                    "--param", "step=all")
    assert series.exit_code == 0, series.output
    assert json.loads((tmp_path / "all" / "series.json").read_text(encoding="utf-8"))["schema"] == "stk.series/1"
    assert json.loads((tmp_path / "all" / "result.00000100.json").read_text(encoding="utf-8"))["schema"] == "stk.graph-result/1"
    assert json.loads((tmp_path / "all" / "result.00000100.output.json").read_text(encoding="utf-8"))["step"] == 100
    assert (tmp_path / "all" / "series.00000100.json").is_file()


def test_series_prints_the_errors_of_each_frame(cli, tmp_path):
    partial = cli.graph(scale={"mode": "fail"})
    partial_file = tmp_path / "partial.json"
    partial_file.write_text(json.dumps(partial))
    result = CliRunner().invoke(graph_cli, ["run", str(partial_file), "--bind", f"run={cli.run}", "--out",
                                            str(cli.out), "--no-cache", "--param", "step=all"])
    assert result.exit_code == 1
    for step in (0, 100, 200):
        assert f"step={step}: error [node_failed]" in result.output and "synthetic failure" in result.output
    assert json.loads((cli.out / "info.00000100.json").read_text(encoding="utf-8"))["step"] == 100  # other outputs still written


def test_doctor_reports_without_failing(cli):
    result = invoke("doctor", "--json", "--timeout", "60")
    document = json.loads(result.output)
    checks = {check["check"]: check for check in document["checks"]}
    assert result.exit_code == 0 and document["ok"]
    assert checks["python"]["status"] == "ok" and "offscreen rendering" in checks
    assert checks["catalog"]["status"] == "ok"


@pytest.mark.render
def test_render_marker_needs_a_working_offscreen_probe(offscreen_probe):
    # Skipped by tests/conftest.py unless `python -m suan.render.offscreen --probe` succeeds in a child process.
    assert offscreen_probe["ok"] and not offscreen_probe["missing"]


def test_helpers(monkeypatch, tmp_path):
    assert _suffix(7) == ".00000007" and _suffix("+x") == ".%2Bx" and _suffix("iso") == ".iso"
    monkeypatch.setenv("STK_GRAPH_CACHE", str(tmp_path / "c"))
    assert default_cache_dir() == tmp_path / "c"


def test_module_entry_points(tmp_path):
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")]),
           "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-m", "suan.graph", "catalog", "--json"], cwd=tmp_path, env=env,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["schema"] == "stk.catalog/1"
    result = subprocess.run([sys.executable, "-m", "suan.cli.main", "graph", "--help"], cwd=tmp_path, env=env,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0 and "validate" in result.stdout and "doctor" in result.stdout
    code = "import sys, suan.graph.cli, suan.graph.catalog, suan.graph.service; assert 'numpy' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


# ---------------------------------------------------------------------------
# The built-in catalog


def test_builtin_catalog_matches_the_spec_for_installed_modules():
    families = catalog.present_families()
    if not families:
        pytest.skip("no built-in node modules are installed yet (sources/filters/analysis/render/view/output/plot)")
    live = catalog.build_registry(entry_points=False).catalog()
    assert catalog.compare_catalog(live, json.loads(SPEC.read_text(encoding="utf-8")), families=families) == []


def _fake_module(name, keep):
    """A stand-in built-in module holding the spec declarations of the given functions."""
    namespace = runpy.run_path(str(M1_NODES), run_name=f"suan.graph.nodes.{name}")
    module = types.ModuleType(f"suan.graph.nodes.{name}")
    for function in keep:
        setattr(module, function, namespace[function])
    return module


def test_catalog_comparison_and_builtin_loading(monkeypatch):
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    monkeypatch.setitem(sys.modules, "suan.graph.nodes.view", _fake_module("view", ["camera", "scene"]))
    assert "view" in catalog.present_families() and "view" not in nodes.missing_modules()
    live = catalog.build_registry(entry_points=False).catalog()
    assert {"stk.view.camera@1", "stk.view.scene@1"} <= {n["id"] for n in live["nodes"]}
    assert catalog.compare_catalog(live, spec, families={"view"}) == []
    assert nodes.catalog()["nodes"] == live["nodes"]
    monkeypatch.setitem(sys.modules, "suan.graph.nodes.view", _fake_module("view", ["camera"]))
    live = catalog.build_registry(entry_points=False).catalog()
    assert catalog.compare_catalog(live, spec, families={"view"}) == ["stk.view.scene@1: missing"]
    changed = json.loads(json.dumps(spec))
    next(n for n in changed["nodes"] if n["id"] == "stk.view.camera@1")["impl_version"] = 2
    assert catalog.compare_catalog(live, changed, families={"view"}) == [
        "stk.view.camera@1: declaration differs from the spec (impl_version)", "stk.view.scene@1: missing"]
    streamlines = catalog.compare_catalog({**spec, "nodes": [n for n in spec["nodes"] if "streamlines" not in n["id"]]},
                                          spec)
    assert streamlines == []  # stretch entries may be absent


class _BrokenFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Makes suan.graph.nodes.plot fail with a missing dependency while it imports."""

    name = "suan.graph.nodes.plot"

    def find_spec(self, fullname, path=None, target=None):
        if fullname == self.name:
            return importlib.machinery.ModuleSpec(fullname, self)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        raise ModuleNotFoundError("No module named 'a_missing_dependency'", name="a_missing_dependency")


def test_only_missing_builtin_modules_are_skipped(monkeypatch):
    for name in nodes.BUILTIN_MODULES:
        monkeypatch.delitem(sys.modules, f"suan.graph.nodes.{name}", raising=False)
    finder = _BrokenFinder()
    monkeypatch.setattr(sys, "meta_path", [finder, *sys.meta_path])
    with pytest.raises(ModuleNotFoundError) as info:
        nodes.builtin_modules()
    assert info.value.name == "a_missing_dependency"
    monkeypatch.setattr(sys, "meta_path", [m for m in sys.meta_path if m is not finder])
    for name in nodes.missing_modules():
        assert importlib.util.find_spec(f"suan.graph.nodes.{name}") is None


def test_entry_point_plugins_override_and_failures_are_reported(monkeypatch):
    class EntryPoint:
        def __init__(self, name, target):
            self.name, self.value, self._target = name, name, target

        def load(self):
            if isinstance(self._target, Exception):
                raise self._target
            return self._target
    namespace = runpy.run_path(str(M1_NODES), run_name="private_plugin")
    points = [EntryPoint("b_broken", ImportError("plugin needs a licence")),
              EntryPoint("a_private", [namespace["camera"]])]
    monkeypatch.setattr(catalog.metadata, "entry_points", lambda group: points if group == "stk.nodes" else [])
    registry = catalog.build_registry()
    assert registry.get("stk.view.camera@1").impl.__module__ == "private_plugin"
    assert registry.load_errors == [("b_broken", "ImportError: plugin needs a licence")]
