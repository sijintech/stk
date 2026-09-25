"""MCP graph tools (suan.mcp.graph_tools); the tool functions are tested directly, registration when mcp is installed."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path

import pytest

from suan.mcp import graph_tools
from suan.mcp.graph_tools import GraphToolError

from test_control_graph import NODE_ENV, muferro_graph  # noqa: F401  (shared graph and SDK environment)


@pytest.fixture
def run_dir(tmp_path):
    from mupro_fake import write_case, write_outputs
    root = tmp_path / "run"
    write_case(root, grid=(4, 3, 2), steps=3, interval=2)
    write_outputs(root, grid=(4, 3, 2), steps=3, interval=2)
    (root / "stk-mupro.json").write_text("{}")  # the launcher record of a run started through STK
    return root


def test_catalog_and_validation_need_no_runtime():
    summary = graph_tools.graph_catalog()
    ids = {node["id"] for node in summary["nodes"]}
    assert {"stk.source.muferro_run@1", "stk.view.scene@1", "stk.plot.line@1"} <= ids
    run = next(n for n in summary["nodes"] if n["id"] == "stk.source.muferro_run@1")
    assert run["params"]["binding"]["widget"] == "binding" and run["required"] == ["binding"]
    assert isinstance(summary["presets"], list) and summary["notes"]
    assert {n["id"].split(".")[1] for n in graph_tools.graph_catalog(family="plot")["nodes"]} == {"plot"}
    full = graph_tools.graph_catalog(node_type="stk.view.camera")
    assert full["id"] == "stk.view.camera@1" and "properties" in full["params"]
    with pytest.raises(GraphToolError, match="Unknown node type"):
        graph_tools.graph_catalog(node_type="stk.nope@1")

    valid = graph_tools.graph_validate(graph=muferro_graph(), parameters={"view": "+x"})
    assert valid["valid"] and len(valid["graph_sha256"]) == 64 and valid["errors"] == []
    assert set(valid["outputs"]) == {"payload", "energy_plot", "energy_png", "energy"}
    invalid = graph_tools.graph_validate(graph=json.dumps(muferro_graph()), parameters={"view": "sideways"})
    assert not invalid["valid"] and "graph_sha256" not in invalid
    assert {"code", "path", "node", "hint", "message"} <= set(invalid["errors"][0])
    for kwargs, message in (({}, "exactly one"), ({"graph": muferro_graph(), "preset": "x"}, "exactly one"),
                            ({"preset": "no-such-preset"}, "Unknown preset"), ({"graph": "{"}, "not JSON")):
        with pytest.raises(GraphToolError, match=message):
            graph_tools.graph_validate(**kwargs)


def test_evaluate_writes_files_and_a_summary(run_dir, tmp_path):
    pytest.importorskip("numpy")
    pytest.importorskip("matplotlib")
    from suan.render.payload import read_directory
    out = tmp_path / "out"
    summary = graph_tools.graph_evaluate(graph=muferro_graph(), bindings={"run": {"dir": str(run_dir)}},
                                         parameters={"step": "latest"}, output_dir=str(out))
    assert summary["output_dir"] == str(out.resolve()) and Path(summary["result_file"]).is_file()
    assert summary["parameters"]["step"] == {"value": 2, "choices": [0, 2]}
    outputs = summary["outputs"]
    payload = outputs["payload"]
    assert payload["type"] == "payload" and payload["file"].endswith("manifest.json") and payload["buffers"] > 0
    assert read_directory(Path(payload["file"]).parent).manifest["schema"] == "stk.payload/2"
    plot = outputs["energy_plot"]
    assert plot["media_type"] == "image/svg+xml" and Path(plot["file"]).read_bytes().lstrip().startswith(b"<")
    assert json.loads(Path(plot["data_file"]).read_text(encoding="utf-8"))["marks"][0]["data"]["y"] == [-1.125, -2.25, -3.375]
    assert Path(outputs["energy_png"]["file"]).read_bytes().startswith(b"\x89PNG")
    energy = outputs["energy"]
    assert energy["rows"] == 3 and energy["columns"]["step"] == [1, 2, 3]
    assert energy["units"]["Total Energy"] == "normalized"
    for bad in ({"run": "relative-or-anything?"}, {"run": {"path": "/x"}}, {"run": 3}):
        with pytest.raises(GraphToolError, match="Binding"):
            graph_tools.graph_evaluate(graph=muferro_graph(), bindings=bad, output_dir=str(out))
    with pytest.raises(GraphToolError, match="not found"):
        graph_tools.graph_evaluate(graph=muferro_graph(), bindings={"run": {"dir": str(tmp_path / "missing")}})
    with pytest.raises(GraphToolError, match="Evaluation failed|Invalid graph"):
        graph_tools.graph_evaluate(graph=muferro_graph(), bindings={}, output_dir=str(out))


def test_render_returns_png_or_a_clear_error(run_dir, tmp_path, offscreen_probe):
    pytest.importorskip("numpy")
    pytest.importorskip("matplotlib")
    bindings = {"run": {"dir": str(run_dir)}}
    # A plot image never needs OpenGL.
    rendered = graph_tools.graph_render(graph=muferro_graph(), bindings=bindings, output="energy_png",
                                        output_dir=str(tmp_path / "plot"))
    assert rendered["png"].startswith(b"\x89PNG") and list(rendered["summary"]["outputs"]) == ["energy_png"]
    with pytest.raises(GraphToolError, match="no output"):
        graph_tools.graph_render(graph=muferro_graph(), bindings=bindings, output="nope")
    with pytest.raises(GraphToolError, match="no image or scene"):
        graph_tools.graph_render(graph={**muferro_graph(), "outputs": {"energy": "run.energy"}}, bindings=bindings)
    # The first scene: rendered offscreen when this host can, otherwise a clear message.
    graph = muferro_graph()
    graph["outputs"] = {"scene": "scene.scene", "energy": "run.energy"}
    if offscreen_probe["ok"]:
        scene = graph_tools.graph_render(graph=graph, bindings=bindings, width=320, height=240,
                                         output_dir=str(tmp_path / "scene"))
        from suan.render.png import png_size
        assert png_size(scene["png"]) == (320, 240)
    else:
        with pytest.raises(GraphToolError, match="Offscreen rendering is unavailable"):
            graph_tools.graph_render(graph=graph, bindings=bindings)


def test_plot_table(tmp_path):
    pytest.importorskip("numpy")
    pytest.importorskip("matplotlib")
    columns = {"step": [1, 2, 3], "Total Energy": [-1.0, -2.0, -2.5], "Landau": [0.5, 0.25, 0.125]}
    rendered = graph_tools.plot_table(columns=columns, x="step", y=["Total Energy", "Landau"],
                                      units={"Total Energy": "normalized"}, title="Energy",
                                      output_dir=str(tmp_path))
    assert rendered["bytes"].startswith(b"\x89PNG") and Path(rendered["summary"]["file"]).is_file()
    data = json.loads(Path(rendered["summary"]["data_file"]).read_text(encoding="utf-8"))
    assert [mark["data"]["y"] for mark in data["marks"]] == [columns["Total Energy"], columns["Landau"]]
    svg = graph_tools.plot_table(columns=columns, y="Landau", kind="scatter", format="svg", output_dir=str(tmp_path))
    assert svg["summary"]["media_type"] == "image/svg+xml"
    assert graph_tools.plot_table(columns={"v": [1, 2, 2, 3]}, kind="hist", output_dir=str(tmp_path))["bytes"]
    with pytest.raises(GraphToolError, match="Unknown column"):
        graph_tools.plot_table(columns=columns, y=["nope"])
    with pytest.raises(GraphToolError, match="kind"):
        graph_tools.plot_table(columns=columns, y="Landau", kind="pie")
    with pytest.raises(GraphToolError, match="columns"):
        graph_tools.plot_table(columns={"a": 1})


def test_default_output_directories_are_private_and_per_call(run_dir, tmp_path, monkeypatch):
    pytest.importorskip("numpy")
    import stat
    import tempfile
    monkeypatch.delenv("STK_MCP_OUTPUT_DIR", raising=False)
    monkeypatch.setenv("STK_GRAPH_CACHE", str(tmp_path / "cache"))
    (tmp_path / "tmp").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))  # stands in for the shared /tmp
    bindings = {"run": {"dir": str(run_dir)}}
    first = graph_tools.graph_evaluate(graph=muferro_graph(), bindings=bindings, parameters={"step": 0},
                                       outputs=["payload"])
    second = graph_tools.graph_evaluate(graph=muferro_graph(), bindings=bindings, parameters={"step": 2},
                                        outputs=["payload"])
    assert first["graph_sha256"] == second["graph_sha256"] and first["output_dir"] != second["output_dir"]
    # The first call's files still hold its own result.
    assert json.loads(Path(first["result_file"]).read_text(encoding="utf-8"))["parameters"]["step"]["value"] == 0
    assert json.loads(Path(second["result_file"]).read_text(encoding="utf-8"))["parameters"]["step"]["value"] == 2
    base = Path(first["output_dir"]).parent
    assert Path(first["output_dir"]).name.startswith(first["graph_sha256"][:16] + "-")
    if hasattr(os, "getuid"):
        assert base == (tmp_path / "tmp" / f"stk-mcp-{os.getuid()}").resolve()
        assert stat.S_IMODE(base.stat().st_mode) == 0o700
        assert stat.S_IMODE(Path(first["output_dir"]).stat().st_mode) == 0o700
        # Somebody else's (or a world-readable) directory, or a planted symlink, is refused.
        os.chmod(base, 0o755)
        with pytest.raises(GraphToolError, match="0700"):
            graph_tools.graph_evaluate(graph=muferro_graph(), bindings=bindings, outputs=["energy"])
        base.rename(tmp_path / "moved")
        base.symlink_to(tmp_path / "moved", target_is_directory=True)
        with pytest.raises(GraphToolError, match="not a directory"):
            graph_tools.graph_evaluate(graph=muferro_graph(), bindings=bindings, outputs=["energy"])


def test_output_files_never_follow_planted_links_or_share_temporary_names(tmp_path):
    from suan.graph.cli import write_atomic
    victim = tmp_path / "victim.txt"
    victim.write_text("precious\n")
    out = tmp_path / "out"
    out.mkdir()
    (out / "energy.svg").symlink_to(victim)
    (out / "energy.svg.part").symlink_to(victim)  # the fixed temporary name of earlier versions
    write_atomic(out / "energy.svg", b"<svg/>")
    assert victim.read_text(encoding="utf-8") == "precious\n"
    assert not (out / "energy.svg").is_symlink() and (out / "energy.svg").read_bytes() == b"<svg/>"
    assert sorted(p.name for p in out.iterdir()) == ["energy.svg", "energy.svg.part"]


def test_concurrent_renders_return_their_own_image(run_dir, tmp_path):
    pytest.importorskip("numpy")
    pytest.importorskip("matplotlib")
    import threading
    from suan.render.png import png_size
    graph = muferro_graph()
    graph["parameters"].append({"name": "w", "type": "integer", "default": 320})
    next(n for n in graph["nodes"] if n["id"] == "energy_png")["params"]["width"] = {"$param": "w"}
    wrong = []

    def render(width):
        rendered = graph_tools.graph_render(graph=graph, bindings={"run": {"dir": str(run_dir)}},
                                            parameters={"w": width}, output="energy_png",
                                            output_dir=str(tmp_path / "shared"))  # one directory for all calls
        if png_size(rendered["png"])[0] != width:
            wrong.append((width, png_size(rendered["png"])[0]))
    for _ in range(2):
        threads = [threading.Thread(target=render, args=(width,)) for width in (320, 480, 640)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(120)
    assert wrong == []


def test_task_bindings_and_events_through_the_runtime(runtime, tmp_path, monkeypatch):
    pytest.importorskip("numpy")
    pytest.importorskip("matplotlib")
    from mupro_fake import make_fake_sdk
    from test_control_graph import muferro_task
    for key in [*NODE_ENV, *(key for key in os.environ if key.startswith("I_MPI_"))]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MUPRO_SDK_PREFIX", str(make_fake_sdk(tmp_path / "sdk")))
    client, supervisor, _, config = runtime
    task_id = muferro_task(client, supervisor)
    monkeypatch.setenv("STK_RUNTIME_URL", client.url)
    monkeypatch.setenv("STK_RUNTIME_TOKEN", config["token"])
    summary = graph_tools.graph_evaluate(graph=muferro_graph(), bindings={"run": f"task:{task_id}"},
                                         outputs=["energy"], output_dir=str(tmp_path / "task"))
    assert summary["outputs"]["energy"]["columns"]["step"] == [1, 2, 3]
    events = graph_tools.get_task_events(task_id)
    assert events["terminal"] and events["events"][0]["type"] == "run.started"
    assert graph_tools.get_task_events(task_id, offset=events["next_offset"], limit=1024)["events"] == []


@pytest.mark.skipif(importlib.util.find_spec("mcp") is None, reason="optional MCP extra")
def test_tools_are_registered():
    from suan.mcp import server
    registered = {tool.name for tool in asyncio.run(server.mcp.list_tools())}
    assert {"graph_catalog", "graph_validate", "graph_evaluate", "graph_render", "plot_table",
            "get_task_events"} <= registered
    assert {"stk_info", "submit_task", "get_task_logs", "download_artifact", "run_stk_command"} <= registered
    summary = asyncio.run(server.graph_catalog(family="view"))
    assert {n["id"] for n in summary["nodes"]} == {"stk.view.camera@1", "stk.view.scene@1"}
