"""Explicit-window LAMMPS property fits; no simulation or project mutation.

Inputs are STK Tables with explicit units. Outputs are summary/fit Tables and
JSON diagnostics. These are finite-time simulation estimates, not validated
material properties. In particular MSD needs a user-selected diffusive regime.
"""
import hashlib
import math

MAX_ROWS = 100000
MAX_TG_POINTS = 500


class AnalysisError(ValueError):
    pass


def _column(table, name, unit):
    if name not in table.fields or table.fields[name].unit != unit:
        raise AnalysisError(f"Column {name!r} must have explicit unit {unit!r}")
    field = table.fields[name]
    if field.components != 1 or field.values.dtype.kind not in "fiu" or field.values.ndim != 1:
        raise AnalysisError(f"Column {name!r} must be numeric scalar data")
    values = list(map(float, table.column(name)))
    if not values or len(values) > MAX_ROWS or not all(math.isfinite(v) for v in values):
        raise AnalysisError(f"Column {name!r} needs 1..{MAX_ROWS} finite values")
    return values


def _number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise AnalysisError(f"{name} must be finite")
    return float(value)


def linear_fit(x, y):
    """Centered ordinary least squares; unweighted, with a free intercept."""
    if len(x) < 3 or len(x) != len(y):
        raise AnalysisError("A fit needs at least three paired observations")
    try:
        mx, my = math.fsum(x) / len(x), math.fsum(y) / len(y)
        dx = [v - mx for v in x]
        xx = math.fsum(v * v for v in dx)
        if xx <= 0:
            raise AnalysisError("Fit coordinate has zero span")
        slope = math.fsum(v * (w - my) for v, w in zip(dx, y)) / xx
        intercept = my - slope * mx
        residual = [w - (my + slope * v) for v, w in zip(dx, y)]
        rss = math.fsum(v * v for v in residual)
        yy = math.fsum((v - my) ** 2 for v in y)
        stderr = math.sqrt((rss / (len(x) - 2)) / xx)
        result = {"slope": slope, "intercept": intercept, "rss": rss, "slope_stderr": stderr,
                  "r_squared": 1 - rss / yy if yy > 0 else None, "samples": len(x), "range": [min(x), max(x)]}
    except (OverflowError, ZeroDivisionError):
        raise AnalysisError("Fit exceeds the finite numerical range") from None
    if not all(math.isfinite(result[key]) for key in ("slope", "intercept", "rss", "slope_stderr")):
        raise AnalysisError("Fit exceeds the finite numerical range")
    return result


def _result(kind, summary, units, x_name, x, y_name, y, fitted, x_unit, y_unit, diagnostics, provenance):
    from suan.data.model import Table
    if provenance is not None:
        # Graph table serialization does not export Dataset provenance. Keep it
        # in diagnostics too, including when a large table becomes a blob.
        diagnostics = {**diagnostics, "source": provenance.to_json()}
    metadata = {"method": kind, "diagnostics": diagnostics,
                "limits": "Unweighted fit; correlated MD samples are not independent uncertainty estimates."}
    return {"summary": Table.from_columns({key: [value] for key, value in summary.items()}, units=units,
                                           id=kind + "_summary", attrs=metadata, provenance=provenance),
            "fit": Table.from_columns({x_name: x, y_name: y, "Fitted": fitted},
                                      units={x_name: x_unit, y_name: y_unit, "Fitted": y_unit},
                                      id=kind + "_fit", attrs=metadata, provenance=provenance),
            "diagnostics": diagnostics}


def tg(table, *, temperature="Temperature", density="Density", split_temperature=None, min_points=3, check=None):
    """Two lines, intersection Tg. Each distinct temperature has equal weight.

Duplicate temperatures are rejected: aggregate equilibrated runs explicitly,
preserving their provenance before passing a density-temperature table here.
An automatic split searches all gaps with enough points on both sides; the
winning intersection must be inside that gap and have the expected slopes.
"""
    t, d = _column(table, temperature, "K"), _column(table, density, "g/cm3")
    if type(min_points) is not int or not 3 <= min_points <= MAX_TG_POINTS // 2:
        raise AnalysisError("min_points must be an integer between 3 and 250")
    if len(t) > MAX_TG_POINTS or len(t) < 2 * min_points:
        raise AnalysisError("Tg needs enough points for two fits and at most 500 temperatures")
    t, d = map(list, zip(*sorted(zip(t, d))))
    if len(set(t)) != len(t) or min(t) <= 0 or min(d) <= 0:
        raise AnalysisError("Tg needs distinct positive temperatures and positive densities")
    if split_temperature is None:
        candidates = range(min_points, len(t) - min_points + 1)
    else:
        split = _number(split_temperature, "split temperature")
        cut = sum(value <= split for value in t)
        if cut < min_points or len(t) - cut < min_points:
            raise AnalysisError("Split leaves too few points in a Tg regime")
        candidates = [cut]
    fits = []
    for cut in candidates:
        if check:
            check()
        low, high = linear_fit(t[:cut], d[:cut]), linear_fit(t[cut:], d[cut:])
        fits.append((low["rss"] + high["rss"], cut, low, high))
    rss, cut, low, high = min(fits, key=lambda item: (item[0], item[1]))
    difference = low["slope"] - high["slope"]
    if difference <= max(1e-14, abs(low["slope"]) * 1e-6) or low["slope"] >= 0 or high["slope"] >= 0:
        raise AnalysisError("No resolved density Tg: require two decreasing lines, steeper at high temperature")
    value = (high["intercept"] - low["intercept"]) / difference
    if not math.isfinite(value) or not t[cut - 1] <= value <= t[cut]:
        raise AnalysisError("Fitted Tg lies outside the split gap; inspect the regimes")
    fitted = [(low if v <= value else high)["intercept"] + (low if v <= value else high)["slope"] * v for v in t]
    diagnostics = {"method": "two independent OLS lines; intersection", "split_gap_K": [t[cut - 1], t[cut]],
                   "low": low, "high": high, "candidates": len(fits), "rss": rss,
                   "uncertainty": "No Tg confidence interval; assess fit windows, replicas and cooling protocol."}
    return _result("tg", {"Tg": value, "LowSlope": low["slope"], "HighSlope": high["slope"], "Samples": len(t)},
                   {"Tg": "K", "LowSlope": "g/cm3/K", "HighSlope": "g/cm3/K", "Samples": "1"},
                   "Temperature", t, "Density", d, fitted, "K", "g/cm3", diagnostics, table.provenance)


def _window(x, y, lower, upper, *, name):
    lower, upper = _number(lower, name + " minimum"), _number(upper, name + " maximum")
    if lower < 0 or upper <= lower:
        raise AnalysisError(f"{name} window must be nonnegative and increasing")
    if any(b <= a for a, b in zip(x, x[1:])):
        raise AnalysisError(f"{name} coordinates must be strictly increasing; do not join reset runs")
    selected = [(v, w) for v, w in zip(x, y) if lower <= v <= upper]
    if len(selected) < 3:
        raise AnalysisError("Fit window contains fewer than three observations")
    return tuple(map(list, zip(*selected)))


def modulus(table, *, strain="Strain", stress="Stress", strain_min=0.0, strain_max=0.02):
    x, y = _column(table, strain, "1"), _column(table, stress, "GPa")
    x, y = _window(x, y, strain_min, strain_max, name="Strain")
    fit = linear_fit(x, y)
    if fit["slope"] <= 0:
        raise AnalysisError("Tensile modulus must be positive; check stress sign and fit regime")
    fitted = [fit["intercept"] + fit["slope"] * v for v in x]
    return _result("modulus", {"Modulus": fit["slope"], "Intercept": fit["intercept"],
                              "SlopeStdError": fit["slope_stderr"], "Samples": len(x)},
                   {"Modulus": "GPa", "Intercept": "GPa", "SlopeStdError": "GPa", "Samples": "1"},
                   "Strain", x, "Stress", y, fitted, "1", "GPa", fit, table.provenance)


def diffusion(table, *, time="Time", msd="MSD", time_min, time_max, dimensions=3):
    """D = slope(MSD)/(2*d); Angstrom^2/fs -> cm^2/s multiplies by 0.1."""
    if type(dimensions) is not int or dimensions not in (1, 2, 3):
        raise AnalysisError("Diffusion dimensions must be 1, 2 or 3")
    x, y = _column(table, time, "fs"), _column(table, msd, "Ao2")
    if min(x) < 0 or min(y) < 0:
        raise AnalysisError("Time and MSD must be nonnegative")
    x, y = _window(x, y, time_min, time_max, name="Time")
    fit = linear_fit(x, y)
    if fit["slope"] <= 0:
        raise AnalysisError("MSD fit must have a positive slope; inspect the diffusive regime")
    factor = 0.1 / (2 * dimensions)
    fitted = [fit["intercept"] + fit["slope"] * v for v in x]
    fit = {**fit, "dimensions": dimensions, "conversion": "Ao2/fs * 0.1 = cm2/s",
           "limits": "Selected MSD components must match dimensions; verify a diffusive regime, group and unwrapped positions."}
    return _result("diffusion", {"Diffusion": fit["slope"] * factor,
                                "SlopeStdError": fit["slope_stderr"] * factor, "Samples": len(x)},
                   {"Diffusion": "cm2/s", "SlopeStdError": "cm2/s", "Samples": "1"},
                   "Time", x, "MSD", y, fitted, "fs", "Ao2", fit, table.provenance)


def _verified_real(text):
    from .log import read_log, verify_log
    styles = [words[1] for line in text.splitlines() if (words := line.split())[:1] == ["units"] and len(words) > 1]
    # A log can contain clear + units + a second simulation. The existing
    # verifier records the last style; earlier blocks must not be mislabeled.
    if not styles or any(style != "real" for style in styles):
        raise AnalysisError("LAMMPS property logs require explicit units real throughout")
    if any(len(block["columns"]) != len(set(block["columns"])) for block in read_log(text)["blocks"]):
        raise AnalysisError("Duplicate thermo column names")
    try:
        verified = verify_log(text)
    except (OverflowError, ValueError):
        raise AnalysisError("Thermodynamic summary exceeds the finite numerical range") from None
    if verified["verification"]["status"] != "passed":
        raise AnalysisError(verified["reason"])
    if verified["units"] != "real":
        raise AnalysisError("LAMMPS property logs require explicit units real throughout")
    return verified


def log_table(text, *, block=-1):
    """One finished thermo block; never concatenate equilibration/production or reset steps."""
    from suan.data.model import Table
    from .log import read_log
    _verified_real(text)
    blocks = read_log(text)["blocks"]
    if type(block) is not int or not -len(blocks) <= block < len(blocks):
        raise AnalysisError("Requested thermo block does not exist")
    selected = blocks[block]
    units = {"Step": "1", "Temp": "K", "Density": "g/cm3", "Press": "atm", "Volume": "Ao3",
             "PotEng": "kcal/mol", "KinEng": "kcal/mol", "TotEng": "kcal/mol", "Time": "fs"}
    columns = selected["columns"]
    if len(columns) != len(set(columns)):
        raise AnalysisError("Duplicate thermo column names")
    return Table.from_columns({name: [row[i] for row in selected["rows"]] for i, name in enumerate(columns)},
                              units={name: units.get(name, "unspecified") for name in columns}, id="lammps_thermo",
                              attrs={"units_style": "real", "block": block, "blocks": len(blocks)})


def density_series(logs):
    """{source label: log text} -> final-block second-half mean T/rho table.

    Callers retain the frozen log files; this utility does no filesystem reads.
    Never combine different unit styles or failed/incomplete runs.
    """
    from suan.data.model import Provenance, Table
    if not isinstance(logs, dict) or not 1 <= len(logs) <= MAX_TG_POINTS:
        raise AnalysisError("Density series requires 1..500 labeled logs")
    temperatures, densities, sources, samples, hashes = [], [], [], [], {}
    for label, text in logs.items():
        if not isinstance(label, str) or not isinstance(text, str):
            raise AnalysisError("Density series requires text labels and log contents")
        result = _verified_real(text)
        qoi = result["qoi"]
        if qoi["density"] is None or qoi["temperature"] is None or qoi["density"] <= 0 or qoi["temperature"] <= 0:
            raise AnalysisError("Density series needs positive Density and Temp columns")
        temperatures.append(qoi["temperature"])
        densities.append(qoi["density"])
        sources.append(label)
        samples.append(qoi["samples"])
        hashes[label] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    provenance = Provenance(activity={"kind": "convert", "id": None},
                            agent={"reader": "stk.lammps.density_series@1"},
                            used=[{"path": label, "sha256": digest, "role": "input_text"}
                                  for label, digest in hashes.items()])
    return Table.from_columns({"Temperature": temperatures, "Density": densities, "Source": sources, "Samples": samples},
                              units={"Temperature": "K", "Density": "g/cm3", "Source": "1", "Samples": "1"},
                              id="density_temperature", provenance=provenance,
                              attrs={"averaging": "last thermo block, second half",
                                     "source_text_sha256": hashes,
                                     "limits": "Retain frozen logs; inspect equilibration and temperature history."})
