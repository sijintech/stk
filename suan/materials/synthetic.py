"""Synthetic test data for the materials models (docs/design/materials-models-s3.md). Labelled synthetic: these curves
only exercise the dataset -> training -> registry -> prediction chain and say nothing about any real material.

- ``pe_loop``: a single-domain Landau-Khalatnikov ferroelectric, dP/dt = -L (2 a P + 4 b P^3 - E), a = a0 (T - Tc),
  swept by a triangular field from -E_max to +E_max and back. Above Tc the response has no hysteresis.
- ``capacity_fade``: a semi-empirical fade, SOH(n) = 1 - k (n/100)^z, with k growing with temperature (Arrhenius), charge
  rate and depth of discharge, plus small measurement noise.

Pure numpy, vectorised over samples; deterministic for a seed.
"""
import numpy as np

from . import curves

GENERATOR_VERSION = 1
MAX_COUNT = 5000  # about 18 s of loops on one core
KINETIC = 2.3e4  # L, cm^2/(uC s) per kV/cm: relaxation of about 10 us, so 100 Hz is nearly quasi-static and 10 kHz is not

PE_INPUTS = [
    {"name": "temperature", "unit": "K", "range": [250.0, 750.0]},
    {"name": "curie_temperature", "unit": "K", "range": [500.0, 800.0]},
    {"name": "landau_a0", "unit": "kV*cm/(uC*K)", "range": [3e-3, 8e-3]},
    {"name": "landau_b", "unit": "kV*cm^5/uC^3", "range": [6e-4, 2e-3]},
    {"name": "e_max", "unit": "kV/cm", "range": [100.0, 300.0]},
    {"name": "frequency", "unit": "Hz", "range": [100.0, 10000.0], "log": True},
]
FADE_INPUTS = [
    {"name": "temperature", "unit": "degC", "range": [10.0, 55.0]},
    {"name": "charge_c_rate", "unit": "C", "range": [0.3, 4.0]},
    {"name": "discharge_c_rate", "unit": "C", "range": [0.5, 3.0]},
    {"name": "depth_of_discharge", "unit": "1", "range": [0.3, 1.0]},
    {"name": "fade_exponent", "unit": "1", "range": [0.5, 0.9]},
]


def _draw(rng, inputs, count):
    values = {}
    for item in inputs:
        low, high = item["range"]
        if item.get("log"):
            values[item["name"]] = np.exp(rng.uniform(np.log(low), np.log(high), count))
        else:
            values[item["name"]] = rng.uniform(low, high, count)
    return values


def pe_loops(values, points=curves.PE_POINTS, substeps=128):
    """P on the up and down branches (``2 * points`` values, uC/cm^2) for each sample in ``values`` (arrays)."""
    a = values["landau_a0"] * (values["temperature"] - values["curie_temperature"])
    b = values["landau_b"]
    e_max, frequency = values["e_max"], values["frequency"]
    count = len(a)
    # Start in equilibrium at -E_max on the negative well: Newton from below the most negative root converges to it.
    p = -np.cbrt(e_max / (4 * b)) - 1.0
    for _ in range(60):
        p = p - (2 * a * p + 4 * b * p ** 3 + e_max) / (2 * a + 12 * b * p ** 2)
    steps = (points - 1) * substeps
    dt = (1.0 / frequency) / (2 * steps)  # a half period per branch
    de = 2 * e_max / steps
    loops = np.empty((count, 2 * points))

    def rate(p_, e_):
        return -KINETIC * (2 * a * p_ + 4 * b * p_ ** 3 - e_)

    for branch in (0, 1):
        sign = 1.0 if branch == 0 else -1.0
        e = -e_max if branch == 0 else e_max
        for step in range(steps + 1):
            if step % substeps == 0:
                index = step // substeps
                loops[:, branch * points + (index if branch == 0 else points - 1 - index)] = p
            if step == steps:
                break
            e_mid, e_next = e + sign * de / 2, e + sign * de
            k1 = rate(p, e)
            k2 = rate(p + dt * k1 / 2, e_mid)
            k3 = rate(p + dt * k2 / 2, e_mid)
            k4 = rate(p + dt * k3, e_next)
            p = p + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6
            e = e_next
    # Stored as both branches over the increasing grid: up branch, then the down branch in increasing field order.
    return loops


def capacity_fades(values, rng, grid=None, noise=0.002):
    grid = curves.FADE_GRID if grid is None else grid
    temperature = values["temperature"] + 273.15
    arrhenius = np.exp(-4000.0 * (1 / temperature - 1 / 298.15))
    k = 0.03 * arrhenius * values["charge_c_rate"] ** 0.6 * values["discharge_c_rate"] ** 0.2 * values["depth_of_discharge"] ** 1.1
    z = values["fade_exponent"]
    soh = 1 - k[:, None] * np.power(grid[None, :] / 100.0, z[:, None])
    soh = soh + rng.normal(0, noise, soh.shape) * (grid[None, :] > 0)
    return np.clip(soh, 0.5, 1.0)  # cells are retired long before half their capacity


def generate(kind, count, seed=0):
    """``count`` samples of ``kind`` ("pe_loop" or "capacity_fade"): (input definitions, list of {inputs, curve})."""
    if kind not in ("pe_loop", "capacity_fade"):
        raise ValueError("kind is pe_loop or capacity_fade")
    if not 1 <= count <= MAX_COUNT:
        raise ValueError(f"count is 1 to {MAX_COUNT}")
    rng = np.random.default_rng(seed)
    inputs = PE_INPUTS if kind == "pe_loop" else FADE_INPUTS
    values = _draw(rng, inputs, count)
    data = pe_loops(values) if kind == "pe_loop" else capacity_fades(values, rng)
    samples = [{"id": f"s{index:05d}", "inputs": {name: float(values[name][index]) for name in values},
                "curve": [float(value) for value in data[index]]} for index in range(count)]
    return [{key: item[key] for key in ("name", "unit")} for item in inputs], samples


__all__ = ["FADE_INPUTS", "GENERATOR_VERSION", "PE_INPUTS", "capacity_fades", "generate", "pe_loops"]
