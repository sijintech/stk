"""Matplotlib renderer of ``stk.plot/1`` specs: PNG, SVG and PDF plus the plotted data as JSON.

Uses ``matplotlib.figure.Figure`` with ``FigureCanvasAgg`` only -- never
``pyplot`` -- so it neither opens windows, nor keeps global figures, nor
switches the process-wide backend; it is safe in services and threads. Style
settings apply through ``matplotlib.rc_context`` for the duration of one call.
Services should point ``MPLCONFIGDIR`` at a writable cache directory.

    from suan.plot.mpl import plot_data, render, render_plot
    png = render(spec, format="png")
    svg = render_plot(spec, format="svg")   # {"bytes", "media_type", "data"}
    data = plot_data(spec)                  # exactly the values that were drawn
"""
import io
import math

from .spec import axis_label, categories_table, check, mark_data

__all__ = ["FORMATS", "MEDIA_TYPES", "STYLES", "build_figure", "plot_data", "render", "render_all", "render_plot"]

FORMATS = ("png", "svg", "pdf")
MEDIA_TYPES = {"png": "image/png", "svg": "image/svg+xml", "pdf": "application/pdf"}
STYLES = {
    "stk-paper": {"font.size": 9.0, "axes.titlesize": 10.0, "axes.labelsize": 9.0, "legend.fontsize": 8.0,
                  "xtick.labelsize": 8.0, "ytick.labelsize": 8.0, "lines.linewidth": 1.4, "axes.linewidth": 0.8,
                  "font.family": "DejaVu Sans"},
    "stk-screen": {"font.size": 11.0, "axes.titlesize": 12.0, "axes.labelsize": 11.0, "legend.fontsize": 10.0,
                   "xtick.labelsize": 10.0, "ytick.labelsize": 10.0, "lines.linewidth": 1.8, "axes.linewidth": 1.0,
                   "font.family": "DejaVu Sans"},
}
_DETERMINISTIC = {"svg.hashsalt": "stk-plot", "svg.fonttype": "path", "pdf.fonttype": 42}


def _np():
    import numpy
    return numpy


def _style_kwargs(style, mark_type):
    style = style or {}
    kw = {}
    if style.get("color"):
        kw["color"] = style["color"]
    if style.get("alpha") is not None:
        kw["alpha"] = style["alpha"]
    if style.get("label") is not None:
        kw["label"] = style["label"]
    if mark_type in ("line", "errorbar"):
        if style.get("linestyle"):
            kw["linestyle"] = "None" if style["linestyle"] == "none" else style["linestyle"]
        if style.get("linewidth") is not None:
            kw["linewidth"] = style["linewidth"]
        if style.get("marker"):
            kw["marker"] = style["marker"]
        if style.get("markersize") is not None:
            kw["markersize"] = style["markersize"]
    return kw


def _pi_ticks(axis):
    from matplotlib.ticker import FuncFormatter, MultipleLocator

    def label(value, _):
        halves = round(value / (math.pi / 2))
        if halves == 0:
            return "0"
        if halves % 2 == 0:
            n = halves // 2
            return "π" if n == 1 else ("−π" if n == -1 else f"{n}π")
        return "π/2" if halves == 1 else ("−π/2" if halves == -1 else f"{halves}π/2")
    axis.set_major_locator(MultipleLocator(math.pi / 2))
    axis.set_major_formatter(FuncFormatter(label))


def _configure_axis(ax, which, config, default_label):
    config = config or {}
    text = axis_label(config, default_label)
    if text:
        getattr(ax, f"set_{which}label")(text)
    if config.get("scale"):
        getattr(ax, f"set_{which}scale")(config["scale"])
    limits = config.get("range")
    if limits and any(v is not None for v in limits):
        getattr(ax, f"set_{which}lim")(*limits)
    if config.get("ticks") == "pi":
        _pi_ticks(getattr(ax, f"{which}axis"))


def _json(values):
    np = _np()
    array = np.asarray(values)
    if array.dtype == object:
        return [None if v is None else (v if isinstance(v, str) else float(v)) for v in array.tolist()]
    if array.dtype.kind == "f":
        return [[None if not math.isfinite(x) else x for x in row] if isinstance(row, list)
                else (None if not math.isfinite(row) else row) for row in array.tolist()]
    return array.tolist()


def _column_units(spec, mark, role):
    data = mark.get("data") or {}
    table = (spec.get("tables") or {}).get(data.get("table")) or {}
    return (table.get("units") or {}).get(data.get(role))


def build_figure(spec, *, metrics=None, dpi=None, size_in=None):
    """``(Figure, plotted)``: the matplotlib figure and the plotted data (see :func:`plot_data`)."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    np = _np()
    check(spec)
    figure_spec = spec.get("figure") or {}
    size = size_in or figure_spec.get("size_in") or [6.0, 4.0]
    fig = Figure(figsize=tuple(size), dpi=dpi or figure_spec.get("dpi", 200), layout="constrained")
    FigureCanvasAgg(fig)
    rows = max(a.get("grid", [0, 0])[0] for a in spec["axes"]) + 1
    cols = max(a.get("grid", [0, 0])[1] for a in spec["axes"]) + 1
    axes, twins = {}, {}
    for config in spec["axes"]:
        row, col = config.get("grid", [0, 0])
        axes[config["id"]] = fig.add_subplot(rows, cols, row * cols + col + 1)
    bar_groups = {}
    for mark in spec["marks"]:
        if mark["type"] == "bar":
            bar_groups.setdefault(mark["axes"], []).append(id(mark))
    plotted = {"schema": "stk.plot-data/1", "marks": []}
    stats = {}
    for index, mark in enumerate(spec["marks"]):
        ax = axes[mark["axes"]]
        if mark.get("y_axis") == "y2":
            if mark["axes"] not in twins:
                twins[mark["axes"]] = ax.twinx()
            ax = twins[mark["axes"]]
        entry = {"index": index, "type": mark["type"], "axes": mark["axes"], "y_axis": mark.get("y_axis", "y"),
                 "label": (mark.get("style") or {}).get("label"),
                 "columns": {role: mark["data"][role] for role in ("x", "y", "z", "u", "v", "yerr", "y2")
                             if role in mark["data"]},
                 "table": mark["data"].get("table")}
        data = mark_data(spec, mark, metrics)
        if data is None:
            entry["skipped"] = "metric data not available"
            plotted["marks"].append(entry)
            continue
        kw = _style_kwargs(mark.get("style"), mark["type"])
        kind = mark["type"]
        if kind == "line":
            ax.plot(data["x"], data["y"], **kw)
        elif kind == "scatter":
            style = mark.get("style") or {}
            ax.scatter(data["x"], data["y"], s=(style.get("markersize") or 4) ** 2, marker=style.get("marker") or "o",
                       **kw)
        elif kind == "errorbar":
            kw.setdefault("capsize", 2)
            ax.errorbar(data["x"], data["y"], yerr=data["yerr"], **kw)
        elif kind == "fill_between":
            kw.setdefault("alpha", 0.3)
            ax.fill_between(data["x"], data["y"], data["y2"], **kw)
        elif kind == "quiver":
            ax.quiver(data["x"], data.get("y", np.zeros_like(data["x"])), data["u"], data["v"], **kw)
        elif kind == "bar":
            _draw_bar(ax, mark, data, kw, bar_groups[mark["axes"]])
        elif kind == "hist":
            _draw_hist(ax, mark, data, kw)
        elif kind == "heatmap":
            _draw_heatmap(fig, ax, spec, mark, data, axes_config=next(a for a in spec["axes"]
                                                                        if a["id"] == mark["axes"]))
        entry["data"] = {role: _json(values) for role, values in data.items()}
        plotted["marks"].append(entry)
        if kind in ("line", "scatter", "errorbar", "bar") and "y" in data and data["y"].dtype != object:
            stats.setdefault(mark["axes"], []).append((kw.get("label") or mark["data"].get("y"), data["y"]))
    for config in spec["axes"]:
        ax = axes[config["id"]]
        marks = [m for m in spec["marks"] if m["axes"] == config["id"]]
        first = next((m for m in marks if m.get("y_axis", "y") == "y"), marks[0] if marks else None)
        x_default = y_default = None
        if first is not None and "table" in first["data"]:
            x_name, y_name = first["data"].get("x"), first["data"].get("y")
            x_unit, y_unit = _column_units(spec, first, "x"), _column_units(spec, first, "y")
            x_default = f"{x_name} [{x_unit}]" if x_name and x_unit else x_name
            y_default = f"{y_name} [{y_unit}]" if y_name and y_unit else y_name
        _configure_axis(ax, "x", config.get("x"), x_default)
        _configure_axis(ax, "y", config.get("y"), y_default)
        if config["id"] in twins:
            second = next(m for m in marks if m.get("y_axis") == "y2")
            y2_name = second["data"].get("y")
            y2_unit = _column_units(spec, second, "y")
            _configure_axis(twins[config["id"]], "y", config.get("y2"),
                            f"{y2_name} [{y2_unit}]" if y2_name and y2_unit else y2_name)
        if config.get("title"):
            ax.set_title(config["title"])
        if config.get("grid_lines"):
            ax.grid(True, alpha=0.3, linewidth=0.6)
        if config.get("aspect") == "equal":
            ax.set_aspect("equal")
        legend = config.get("legend", {"loc": "best"})
        if legend is not False:
            handles, labels = ax.get_legend_handles_labels()
            if config["id"] in twins:
                more = twins[config["id"]].get_legend_handles_labels()
                handles, labels = handles + more[0], labels + more[1]
            if handles:
                ax.legend(handles, labels, loc=(legend or {}).get("loc", "best"))
        if config.get("stats") and stats.get(config["id"]):
            lines = []
            for label, values in stats[config["id"]]:
                finite = values[np.isfinite(values)]
                if len(finite):
                    lines.append(f"{label}: min {finite.min():.4g}  max {finite.max():.4g}  mean {finite.mean():.4g}")
            if lines:
                ax.text(0.02, 0.98, "\n".join(lines), transform=ax.transAxes, va="top", ha="left",
                        fontsize="small", family="monospace",
                        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.8, "edgecolor": "0.7"})
    if figure_spec.get("title"):
        fig.suptitle(figure_spec["title"])
    return fig, plotted


def _draw_bar(ax, mark, data, kw, group):
    np = _np()
    x, y = data["x"], data["y"]
    horizontal = y.dtype == object and x.dtype != object
    categories, values = (y, x) if horizontal else (x, y)
    labels = [str(v) for v in categories]
    count, slot = len(group), group.index(id(mark))
    width = 0.8 / count
    positions = np.arange(len(labels)) - 0.4 + width * (slot + 0.5)
    style = mark.get("style") or {}
    if style.get("colors"):
        kw = {**kw, "color": list(style["colors"])[:len(labels)]}
    if horizontal:
        ax.barh(positions, values.astype(float), height=width, log=bool(mark.get("log")), **kw)
        ax.set_yticks(np.arange(len(labels)), labels)
    else:
        ax.bar(positions, values.astype(float), width=width, log=bool(mark.get("log")), **kw)
        ax.set_xticks(np.arange(len(labels)), labels, rotation=45 if max((len(s) for s in labels), default=0) > 6
                      else 0, ha="right" if max((len(s) for s in labels), default=0) > 6 else "center")


def _draw_hist(ax, mark, data, kw):
    np = _np()
    bins = int(mark.get("bins", 64))
    limits = mark.get("range")
    if "y" in data:                         # pre-binned: x = centres, y = counts / densities
        centres, weights = data["x"].astype(float), data["y"].astype(float)
        if limits and None not in limits:
            edges = np.linspace(limits[0], limits[1], bins + 1)
        else:
            step = np.diff(centres).mean() if len(centres) > 1 else 1.0
            edges = np.concatenate([centres - step / 2, [centres[-1] + step / 2]]) if len(centres) else [0, 1]
        ax.hist(centres, bins=edges, weights=np.nan_to_num(weights), log=bool(mark.get("log")), **kw)
    else:
        values = data["x"].astype(float)
        values = values[np.isfinite(values)]
        hist_range = tuple(limits) if limits and None not in limits else None
        ax.hist(values, bins=bins, range=hist_range, density=bool(mark.get("density")), log=bool(mark.get("log")),
                **kw)


def _draw_heatmap(fig, ax, spec, mark, data, axes_config):
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch
    np = _np()
    z = data["z"]
    table = mark["data"]["table"]
    categories = categories_table(spec, table)
    categorical = mark.get("categorical", categories is not None)
    extent = mark.get("extent")
    aspect = axes_config.get("aspect", "auto")
    style = mark.get("style") or {}
    if categorical and categories:
        ordered = sorted(categories, key=lambda c: c[0])
        values = [int(v) for v, _, _ in ordered]
        cmap = ListedColormap([color or "#808080" for _, _, color in ordered])
        norm = BoundaryNorm([v - 0.5 for v in values] + [values[-1] + 0.5], cmap.N)
        ax.imshow(z, origin="lower", extent=extent, aspect=aspect, cmap=cmap, norm=norm, interpolation="nearest")
        present = set(int(v) for v in np.unique(z[np.isfinite(z)]))
        handles = [Patch(facecolor=color or "#808080", edgecolor="0.4", label=str(name))
                   for value, name, color in ordered if int(value) in present]
        if handles:
            ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize="small",
                      frameon=False)
        return
    limits = mark.get("range") or [None, None]
    image = ax.imshow(z, origin="lower", extent=extent, aspect=aspect, cmap=style.get("cmap", "viridis"),
                      vmin=limits[0], vmax=limits[1], interpolation="nearest")
    if "colorbar" in mark:
        bar = fig.colorbar(image, ax=ax)
        label = (mark.get("colorbar") or {}).get("label")
        if label:
            bar.set_label(label)


def render(spec, *, format="png", dpi=None, width_px=None, height_px=None, magnification=1, transparent=False,
           metrics=None):
    """Bytes of the plot as ``png``, ``svg`` or ``pdf``.

    ``width_px``/``height_px`` override ``figure.size_in`` at the spec's dpi;
    ``magnification`` multiplies the dpi (same picture, more pixels).
    """
    if format not in FORMATS:
        raise ValueError(f"Unknown plot format {format!r}; expected one of {', '.join(FORMATS)}")
    return _render(spec, format=format, dpi=dpi, width_px=width_px, height_px=height_px,
                   magnification=magnification, transparent=transparent, metrics=metrics)


def _render(spec, *, format, dpi, width_px, height_px, magnification, transparent, metrics, plotted=None):
    import matplotlib
    figure_spec = spec.get("figure") or {}
    base_dpi = int(dpi or figure_spec.get("dpi", 200))
    size = list(figure_spec.get("size_in") or [6.0, 4.0])
    if width_px:
        size[0] = width_px / base_dpi
    if height_px:
        size[1] = height_px / base_dpi
    style = STYLES.get(figure_spec.get("style", "stk-paper"), STYLES["stk-paper"])
    with matplotlib.rc_context({**style, **_DETERMINISTIC}):
        fig, data = build_figure(spec, metrics=metrics, dpi=base_dpi, size_in=size)
        if plotted is not None:
            plotted["plotted"] = data
        buffer = io.BytesIO()
        metadata = {"Software": None} if format == "png" else ({"Date": None} if format == "svg" else
                                                               {"CreationDate": None})
        fig.savefig(buffer, format=format, dpi=base_dpi * int(magnification), transparent=transparent,
                    metadata=metadata)
    return buffer.getvalue()


def render_plot(plot, *, format="svg", dpi=None, width_px=None, height_px=None, magnification=1, transparent=False,
                metrics=None):
    """``{"bytes", "media_type", "data"}``: the rendered plot and the plotted data (one figure build)."""
    if format not in FORMATS:
        raise ValueError(f"Unknown plot format {format!r}; expected one of {', '.join(FORMATS)}")
    data = {}
    content = _render(plot, format=format, dpi=dpi, width_px=width_px, height_px=height_px,
                      magnification=magnification, transparent=transparent, metrics=metrics, plotted=data)
    return {"bytes": content, "media_type": MEDIA_TYPES[format], "data": data["plotted"]}


def render_all(spec, formats=("png", "svg"), **kw):
    """``{format: bytes}`` for several formats."""
    return {fmt: render(spec, format=fmt, **kw) for fmt in formats}


def plot_data(spec, *, metrics=None):
    """The plotted data: ``{"schema": "stk.plot-data/1", "marks": [{index, type, axes, y_axis, label, table,
    columns {role: column}, data {role: [...]}}]}`` (non-finite values as ``null``)."""
    import matplotlib
    with matplotlib.rc_context(_DETERMINISTIC):
        _, plotted = build_figure(spec, metrics=metrics)
    return plotted
