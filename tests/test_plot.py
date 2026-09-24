"""stk.plot/1 rendering with matplotlib Figure + FigureCanvasAgg (never pyplot)."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("matplotlib")

from mupro_fake import write_outputs  # noqa: E402
from suan.data.model import Table  # noqa: E402
from suan.mupro.run import ENERGY_ROW  # noqa: E402
from suan.plot.mpl import plot_data, render, render_all, render_plot  # noqa: E402
from suan.plot.spec import PlotSpecError, check, select_rows, table_payload, validate  # noqa: E402
from suan.render.png import decode_png, png_size  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NAMES = ["Elastic Energy", "Electric Energy", "Landau Energy", "Gradient P Energy", "Total Energy"]


def energy_table(tmp_path, steps=12):
    """Parse a fake muFerro energy_out.dat (the format of suan/mupro/run.py) into a Table."""
    write_outputs(tmp_path, steps=steps, interval=4)
    rows = []
    for line in (tmp_path / "energy_out.dat").read_text(encoding="utf-8").splitlines()[1:]:
        match = ENERGY_ROW.fullmatch(line)
        rows.append([int(match[1])] + [float(v) for v in match[2].split()])
    data = np.array(rows)
    columns = {"step": data[:, 0].astype(np.int64), **{name: data[:, i + 1] for i, name in enumerate(NAMES)}}
    return Table.from_columns(columns, units={name: "normalized" for name in NAMES}, id="energy", index="step"), data


def line_spec(table, **marks):
    columns = ["step", "Elastic Energy", "Total Energy"]
    return {"schema": "stk.plot/1", "figure": {"size_in": [4, 3], "dpi": 80, "title": "energy"},
            "axes": [{"id": "a0", "x": {"label": "Step"}, "y": {"label": "Energy", "unit": "normalized"},
                      "y2": {"label": "Total"}, "legend": {"loc": "best"}, "grid_lines": True, "stats": True}],
            "marks": [{"type": "line", "axes": "a0", "data": {"table": "energy", "x": "step", "y": "Elastic Energy",
                                                                **marks}, "style": {"color": "C0", "label": "Elastic"}},
                      {"type": "line", "axes": "a0", "y_axis": "y2",
                       "data": {"table": "energy", "x": "step", "y": "Total Energy"},
                       "style": {"color": "C3", "linestyle": "--", "marker": "o"}}],
            "tables": {"energy": table_payload(table, columns)}}


def test_line_plot_png_svg_pdf_and_data_equal_the_parsed_columns(tmp_path):
    table, data = energy_table(tmp_path)
    spec = check(line_spec(table))
    outputs = render_all(spec, formats=("png", "svg", "pdf"))
    assert outputs["png"].startswith(b"\x89PNG") and png_size(outputs["png"]) == (320, 240)
    assert outputs["svg"].lstrip().startswith(b"<?xml") and b"<svg" in outputs["svg"]
    assert outputs["pdf"].startswith(b"%PDF")
    plotted = plot_data(spec)
    assert plotted["schema"] == "stk.plot-data/1"
    first, second = plotted["marks"]
    assert first["data"]["x"] == data[:, 0].tolist() and first["data"]["y"] == data[:, 1].tolist()
    assert second["y_axis"] == "y2" and second["data"]["y"] == data[:, 5].tolist()
    assert first["columns"] == {"x": "step", "y": "Elastic Energy"} and first["label"] == "Elastic"
    json.dumps(plotted)
    result = render_plot(spec, format="svg")
    assert result["media_type"] == "image/svg+xml" and result["bytes"] == outputs["svg"]
    assert result["data"] == plotted
    assert render_plot(spec, format="png")["media_type"] == "image/png"


def test_rendering_is_deterministic():
    table = Table.from_columns({"t": np.arange(5.0), "v": np.arange(5.0) ** 2})
    spec = {"schema": "stk.plot/1", "axes": [{"id": "a"}],
            "marks": [{"type": "scatter", "axes": "a", "data": {"table": "t", "x": "t", "y": "v"}}],
            "tables": {"t": table_payload(table)}}
    assert render(spec, format="svg") == render(spec, format="svg")
    assert render(spec, format="pdf") == render(spec, format="pdf")
    assert render(spec, format="png") == render(spec, format="png")


def test_filters_stride_and_last_n(tmp_path):
    table, data = energy_table(tmp_path, steps=20)
    spec = line_spec(table, filter=[{"column": "step", "op": ">=", "value": 3},
                                    {"column": "Elastic Energy", "op": "<", "value": 27}], stride=2, last_n=4)
    x = plot_data(spec)["marks"][0]["data"]["x"]
    kept = [s for s in data[:, 0] if s >= 3 and 1.5 * s < 27][::2][-4:]
    assert x == kept
    index = select_rows(spec, "energy", {"filter": [{"column": "step", "op": "!=", "value": 1}]})
    assert 0 not in index.tolist() and len(index) == 19


def test_pyplot_is_never_used_and_the_backend_is_unchanged(tmp_path):
    # The raw rcParams value is compared: matplotlib.get_backend() itself would import pyplot.
    code = ("import json, sys, matplotlib; raw = lambda: dict.__getitem__(matplotlib.rcParams, 'backend'); "
            "before = raw(); from suan.plot.mpl import render; from suan.plot.spec import check; "
            "spec = check({'schema': 'stk.plot/1', 'axes': [{'id': 'a'}], 'marks': [{'type': 'line', 'axes': 'a', "
            "'data': {'table': 't', 'y': 'v'}}], 'tables': {'t': {'columns': {'v': [1, 2, 3]}}}}); "
            "[render(spec, format=f) for f in ('png', 'svg', 'pdf')]; "
            "print(json.dumps(['matplotlib.pyplot' in sys.modules, before is raw() or before == raw()]))")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path), "MPLCONFIGDIR": str(tmp_path)}
    output = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, env=env).stdout
    assert json.loads(output.strip().splitlines()[-1]) == [False, True]
    if "matplotlib.pyplot" in sys.modules:           # another test imported pyplot: we must not add figures
        pyplot = sys.modules["matplotlib.pyplot"]
        before = pyplot.get_fignums()
        render({"schema": "stk.plot/1", "axes": [{"id": "a"}], "marks": [
            {"type": "line", "axes": "a", "data": {"table": "t", "y": "v"}}], "tables": {"t": {"columns": {"v": [1]}}}})
        assert pyplot.get_fignums() == before


def test_bar_hist_heatmap_errorbar_fill_quiver_marks_render():
    tables = {"f": {"columns": {"name": ["T[100]", "O[110]", "R[111]"], "fraction": [0.5, 0.3, None],
                                "err": [0.05, 0.02, 0.01], "lo": [0.4, 0.2, 0.1]}},
              "h": {"columns": {"c": [0.5, 1.5, 2.5], "n": [3, 5, 1]}, "units": {"c": "nm"}},
              "s": {"columns": {"z": [[0, 1, 2], [3, 4, 5]]}, "shape": [2, 3]},
              "lab": {"columns": {"z": [[1, 1, 7], [7, 19, -1]]}},
              "lab/categories": {"columns": {"value": [-1, 1, 7, 19], "name": ["none", "T", "O", "R"],
                                             "color": ["#ffffff", "#ff0000", "#00ff00", "#0000ff"]}},
              "q": {"columns": {"x": [0, 1], "y": [0, 1], "u": [1, 0], "v": [0, 1]}}}
    spec = {"schema": "stk.plot/1", "figure": {"size_in": [8, 6], "dpi": 60, "style": "stk-screen"},
            "axes": [{"id": "bars", "grid": [0, 0]}, {"id": "hist", "grid": [0, 1], "x": {"ticks": "pi"}},
                     {"id": "heat", "grid": [1, 0], "aspect": "equal"}, {"id": "cat", "grid": [1, 1]},
                     {"id": "misc", "grid": [2, 0], "x": {"scale": "log", "range": [0.1, None]}},
                     {"id": "flow", "grid": [2, 1]}],
            "marks": [{"type": "bar", "axes": "bars", "data": {"table": "f", "x": "name", "y": "fraction"},
                       "style": {"colors": ["#ff0000", "#00ff00", "#0000ff"]}},
                      {"type": "bar", "axes": "bars", "data": {"table": "f", "x": "fraction", "y": "name"}},
                      {"type": "hist", "axes": "hist", "data": {"table": "h", "x": "c", "y": "n"}, "bins": 3,
                       "range": [0, 3]},
                      {"type": "hist", "axes": "hist", "data": {"table": "h", "x": "c"}, "bins": 2, "density": True},
                      {"type": "heatmap", "axes": "heat", "data": {"table": "s", "z": "z"}, "colorbar": {"label": "z"},
                       "extent": [0, 3, 0, 2], "style": {"cmap": "cividis"}},
                      {"type": "heatmap", "axes": "cat", "data": {"table": "lab", "z": "z"}},
                      {"type": "errorbar", "axes": "misc", "data": {"table": "f", "x": "lo", "y": "fraction",
                                                                    "yerr": "err"}},
                      {"type": "fill_between", "axes": "misc", "data": {"table": "f", "x": "lo", "y": "lo",
                                                                        "y2": "fraction"}},
                      {"type": "quiver", "axes": "flow", "data": {"table": "q", "x": "x", "y": "y", "u": "u",
                                                                  "v": "v"}}],
            "tables": tables}
    assert validate(spec) == []
    png = render(spec, format="png", magnification=2)
    assert png_size(png) == (960, 720)
    image = decode_png(png)
    for rgb in ((255, 0, 0), (0, 255, 0), (0, 0, 255)):
        assert (np.abs(image[..., :3].astype(int) - rgb).max(axis=-1) <= 2).sum() > 50
    marks = plot_data(spec)["marks"]
    assert marks[0]["data"]["y"] == [0.5, 0.3, None] and marks[5]["data"]["z"] == [[1, 1, 7], [7, 19, -1]]


def test_metric_marks_use_supplied_series_or_are_skipped():
    spec = {"schema": "stk.plot/1", "axes": [{"id": "a"}],
            "marks": [{"type": "line", "axes": "a", "data": {"metric": {"names": ["total_energy"]}}}]}
    assert plot_data(spec)["marks"][0]["skipped"] == "metric data not available"
    data = plot_data(spec, metrics={"total_energy": {"x": [1, 2], "y": [3.0, math.nan]}})
    assert data["marks"][0]["data"] == {"x": [1.0, 2.0], "y": [3.0, None]}


@pytest.mark.parametrize("mutate, message", [
    (lambda s: s.update(schema="stk.plot/2"), "schema"),
    (lambda s: s["marks"][0].update(axes="zz"), "unknown axes"),
    (lambda s: s["marks"][0]["data"].update(y="nope"), "no column"),
    (lambda s: s["marks"][0]["data"].update(table="nope"), "unknown table"),
    (lambda s: s["marks"][0].update(type="pie"), "must be one of"),
    (lambda s: s["axes"].append({"id": "a0"}), "unique"),
    (lambda s: s["marks"][0]["data"].update(filter=[{"column": "zz", "op": ">", "value": 1}]), "no column"),
    (lambda s: s["marks"][0]["data"].pop("y"), "needs data.y"),
])
def test_invalid_specs_are_rejected(tmp_path, mutate, message):
    table, _ = energy_table(tmp_path, steps=3)
    spec = line_spec(table)
    mutate(spec)
    with pytest.raises(PlotSpecError, match=message):
        check(spec)
    with pytest.raises(ValueError):
        render(line_spec(table), format="gif")
