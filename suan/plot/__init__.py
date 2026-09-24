"""STK 2D plots: ``stk.plot/1`` specs (``suan.plot.spec``) rendered by matplotlib (``suan.plot.mpl``).

Rendering uses ``matplotlib.figure.Figure`` + ``FigureCanvasAgg`` only (never
pyplot) and returns PNG/SVG/PDF bytes plus the plotted data as JSON.
Importing this package imports nothing heavy.

Services call :func:`ensure_mplconfigdir` before matplotlib is first imported,
so its font cache lives in a writable directory of their own cache instead of a
home directory the service account may not be able to write.
"""
import os
from pathlib import Path

__all__ = ["ensure_mplconfigdir"]


def ensure_mplconfigdir(cache_root):
    """Point ``MPLCONFIGDIR`` at ``<cache_root>/matplotlib`` (created with mode 0700) unless it is already set.

    Returns the directory in use, or ``None`` when ``cache_root`` is not writable (matplotlib then falls
    back to its own choice). matplotlib reads the variable once, at import: call this first. Several
    processes may share the directory (matplotlib locks its font cache while writing it).
    """
    current = os.environ.get("MPLCONFIGDIR")
    if current:
        return Path(current)
    path = Path(cache_root).expanduser() / "matplotlib"
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        return None
    if not os.access(path, os.W_OK):
        return None
    os.environ["MPLCONFIGDIR"] = str(path)
    return path
