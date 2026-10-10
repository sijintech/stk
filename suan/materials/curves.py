"""The two curve targets of the materials models (docs/design/materials-models-s3.md) and the numbers read from them.

- ``pe_loop``: polarization P (uC/cm^2) on a normalized field grid x = E / E_max from -1 to 1, ``PE_POINTS`` points on
  the up branch (field increasing) followed by ``PE_POINTS`` on the down branch, both in increasing x. Read: remanent
  polarization P_r and coercive field E_c (half the gap between the branches at E = 0 and at P = 0), saturation P_s.
- ``capacity_fade``: state of health SOH = Q(n) / Q(0) on a cycle grid 0 to 2000, ``FADE_POINTS`` points; null where a
  measurement ended. Read: cycle life (first cycle at which SOH reaches 0.8), or null when it stays above.
"""
import math

import numpy as np

PE_POINTS = 64
PE_GRID = np.linspace(-1.0, 1.0, PE_POINTS)
FADE_POINTS = 64
FADE_GRID = np.linspace(0.0, 2000.0, FADE_POINTS)
END_OF_LIFE = 0.8
KINDS = ("pe_loop", "capacity_fade")


def length(kind):
    return 2 * PE_POINTS if kind == "pe_loop" else FADE_POINTS


def grid(kind):
    """The grid as stored in a dataset (normalized field, or cycle numbers)."""
    if kind == "pe_loop":
        return {"x": "E/E_max", "points": PE_POINTS, "branches": ["up", "down"], "from": -1.0, "to": 1.0}
    return {"x": "cycle", "points": FADE_POINTS, "from": 0.0, "to": 2000.0}


def _crossing(x, y, level=0.0):
    """The first x where y reaches ``level`` (linear interpolation, including the last point), or None."""
    for i in range(len(x)):
        a = y[i] - level
        if a == 0:
            return float(x[i])
        if i + 1 < len(x):
            b = y[i + 1] - level
            if a * b < 0:
                return float(x[i] - a * (x[i + 1] - x[i]) / (b - a))
    return None


def _finite(value):
    return value if value is not None and math.isfinite(value) else None


def readout(kind, curve, inputs=None):
    """The scalar numbers of a curve: for a loop {remanent_polarization, coercive_field, saturation_polarization}
    (E_c in kV/cm when ``inputs`` has e_max, else as a fraction of E_max); for a fade {cycle_life}."""
    values = [math.nan if value is None else float(value) for value in curve]
    if kind == "pe_loop":
        # Missing points are left out of each branch; a number that cannot be read is None (never NaN).
        up, down = np.array(values[:PE_POINTS]), np.array(values[PE_POINTS:])
        known_up, known_down = ~np.isnan(up), ~np.isnan(down)
        if known_up.sum() < 2 or known_down.sum() < 2:
            return {"remanent_polarization": None, "coercive_field": None, "saturation_polarization": None}
        grid_up, grid_down, up, down = PE_GRID[known_up], PE_GRID[known_down], up[known_up], down[known_down]
        p_up, p_down = float(np.interp(0.0, grid_up, up)), float(np.interp(0.0, grid_down, down))
        e_up, e_down = _crossing(grid_up, up), _crossing(grid_down, down)
        scale = float((inputs or {}).get("e_max", 1.0))
        coercive = None if e_up is None or e_down is None else abs(e_up - e_down) / 2 * abs(scale)
        return {"remanent_polarization": _finite(abs(p_down - p_up) / 2), "coercive_field": _finite(coercive),
                "saturation_polarization": _finite(float(max(abs(up[-1]), abs(down[0]))))}
    soh = np.array(values)
    known = ~np.isnan(soh)
    if known.sum() < 2:
        return {"cycle_life": None}
    grid_known, soh = FADE_GRID[known], soh[known]
    life = 0.0 if soh[0] <= END_OF_LIFE else _crossing(grid_known, soh, END_OF_LIFE)
    return {"cycle_life": _finite(life)}


__all__ = ["END_OF_LIFE", "FADE_GRID", "FADE_POINTS", "KINDS", "PE_GRID", "PE_POINTS", "grid", "length", "readout"]
