"""Known physical relationships, invalid regimes and graph execution for E1c."""
import hashlib
import math
from pathlib import Path

import numpy as np
import pytest

from suan.data.model import Table
from suan.lammps.analysis import AnalysisError, density_series, diffusion, linear_fit, log_table, modulus, tg


def density_table():
    temperatures = [250, 275, 300, 325, 350, 375, 400, 425]
    return Table.from_columns({"Temperature": temperatures,
                               "Density": [1.4 - 0.0002*(t-250) - 0.0005*max(0, t-340) for t in temperatures]},
                              units={"Temperature": "K", "Density": "g/cm3"})


def stress_table():
    strains = [0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.04]
    return Table.from_columns({"Strain": strains, "Stress": [0.125+2.5*x if x <= 0.02 else 0.25 for x in strains]},
                              units={"Strain": "1", "Stress": "GPa"})


def msd_table():
    times = [0, 100, 500, 1000, 2000, 5000, 10000]
    # Ballistic early part, then D=1e-4 cm2/s in three dimensions.
    return Table.from_columns({"Time": times, "MSD": [0.000006*t*t if t < 1000 else 0.2+0.006*t for t in times]},
                              units={"Time": "fs", "MSD": "Ao2"})


def scalar(result, name):
    return result["summary"].column(name)[0]


def test_tg_known_intersection_and_explicit_regimes_without_mutation():
    table = density_table()
    before = table.to_json()
    for split in (None, 337):
        result = tg(table, split_temperature=split)
        assert scalar(result, "Tg") == pytest.approx(340, abs=1e-8)
        assert scalar(result, "LowSlope") == pytest.approx(-0.0002)
        assert scalar(result, "HighSlope") == pytest.approx(-0.0007)
        assert result["diagnostics"]["split_gap_K"] == [325, 350]
        assert result["summary"].fields["Tg"].unit == "K"
        assert np.allclose(result["fit"].column("Fitted"), table.column("Density"))
    assert table.to_json() == before
    shuffled = Table.from_columns({"Temperature": table.column("Temperature")[::-1],
                                   "Density": table.column("Density")[::-1]}, units=before["units"])
    assert scalar(tg(shuffled), "Tg") == pytest.approx(340)


def test_modulus_keeps_preload_intercept_and_excludes_plastic_region():
    result = modulus(stress_table(), strain_max=0.02)
    assert scalar(result, "Modulus") == pytest.approx(2.5)
    assert scalar(result, "Intercept") == pytest.approx(0.125)
    assert scalar(result, "Samples") == 5
    assert result["summary"].fields["Modulus"].unit == "GPa"
    assert result["diagnostics"]["r_squared"] == pytest.approx(1)
    assert result["diagnostics"]["slope_stderr"] < 1e-12


def test_einstein_diffusion_unit_conversion_window_and_dimensions():
    result = diffusion(msd_table(), time_min=1000, time_max=10000)
    assert scalar(result, "Diffusion") == pytest.approx(1e-4)
    assert scalar(result, "Samples") == 4
    assert result["summary"].fields["Diffusion"].unit == "cm2/s"
    assert result["diagnostics"]["slope"] == pytest.approx(0.006)
    for dimensions in (1, 2):
        fit = diffusion(msd_table(), time_min=1000, time_max=10000, dimensions=dimensions)
        assert scalar(fit, "Diffusion") == pytest.approx(3e-4/dimensions)


def test_centered_regression_handles_offset_and_reports_residuals():
    x = [1e12+i for i in range(5)]
    fit = linear_fit(x, [3*i+0.1*(-1)**i for i in range(5)])
    assert fit["slope"] == pytest.approx(3)
    assert fit["rss"] > 0 and fit["slope_stderr"] > 0 and 0 < fit["r_squared"] < 1
    with pytest.raises(AnalysisError, match="numerical range"):
        linear_fit([1e308, 1e308/2, 1e308/3], [1, 2, 3])


@pytest.mark.parametrize("change", [
    lambda t: setattr(t.fields["Temperature"], "unit", "Cel"),
    lambda t: t.column("Temperature").__setitem__(1, t.column("Temperature")[0]),
    lambda t: t.column("Density").__setitem__(1, float("nan")),
    lambda t: t.column("Density").__setitem__(1, -0.2),
])
def test_tg_invalid_inputs_are_not_silently_dropped(change):
    table = density_table()
    change(table)
    with pytest.raises(AnalysisError):
        tg(table)


def test_tg_rejects_a_single_line_wrong_slopes_outside_gap_and_too_few_points():
    table = density_table()
    table.fields["Density"].values = np.array([1.5-0.0001*t for t in table.column("Temperature")])
    with pytest.raises(AnalysisError, match="resolved"):
        tg(table)
    with pytest.raises(AnalysisError, match="too few"):
        tg(density_table(), split_temperature=260)
    with pytest.raises(AnalysisError):
        tg(density_table(), min_points=5)
    with pytest.raises(AnalysisError):
        tg(density_table(), min_points=True)
    table.fields["Density"].values = np.array([1.4-0.0007*(t-250)+0.0005*max(0, t-340)
                                             for t in table.column("Temperature")])
    with pytest.raises(AnalysisError, match="resolved"):
        tg(table)
    table = density_table()
    table.column("Density")[4:] -= 0.05
    with pytest.raises(AnalysisError, match="outside"):
        tg(table, split_temperature=337)


@pytest.mark.parametrize("window", [(0, 100), (1000, 1000), (-1, 10000), (10000, 1000), (0, float("inf"))])
def test_diffusion_bad_windows_are_rejected(window):
    with pytest.raises(AnalysisError):
        diffusion(msd_table(), time_min=window[0], time_max=window[1])


def test_invalid_units_signs_reset_time_and_dimensions_fail():
    table = stress_table()
    table.fields["Stress"].unit = "atm"
    with pytest.raises(AnalysisError, match="GPa"):
        modulus(table)
    table = stress_table()
    table.column("Stress")[:] *= -1
    with pytest.raises(AnalysisError, match="positive"):
        modulus(table)
    for dimensions in (0, 4, True, 1.5):
        with pytest.raises(AnalysisError):
            diffusion(msd_table(), time_min=1000, time_max=10000, dimensions=dimensions)
    table = msd_table()
    table.column("Time")[-1] = 0
    with pytest.raises(AnalysisError, match="strictly"):
        diffusion(table, time_min=1000, time_max=10000)
    table = msd_table()
    table.column("MSD")[0] = -1
    with pytest.raises(AnalysisError, match="nonnegative"):
        diffusion(table, time_min=1000, time_max=10000)


def test_log_reader_keeps_one_complete_block_and_requires_real_units():
    text = (Path(__file__).parent / "data/lammps/pet-npt.log").read_text()
    last, first = log_table(text), log_table(text, block=0)
    assert last.n_rows == 21 and first.n_rows == 2
    assert last.fields["Density"].unit == "g/cm3" and last.fields["Temp"].unit == "K"
    for invalid in (text.replace("units real", "units metal"), text + "ERROR: Lost atoms\n",
                    text[:text.rindex("Loop time of")], text.replace("1.2052615", "nan")):
        with pytest.raises(AnalysisError):
            log_table(invalid)
    with pytest.raises(AnalysisError):
        log_table(text, block=2)
    series = density_series({"first": text, "second": text.replace("units real", "units real")})
    assert series.n_rows == 2 and series.column("Samples").tolist() == [11, 11]
    assert series.column("Density")[0] == pytest.approx(1.2225, abs=1e-4)
    with pytest.raises(AnalysisError):
        density_series({"bad": text.replace("units real", "units metal")})


@pytest.mark.parametrize("kind", ["tg", "modulus", "diffusion"])
def test_graph_presets_produce_inspectable_tables_plots_and_provenance(tmp_path, kind):
    from suan.graph.resolve import LocalDirResolver
    from suan.graph.service import MemoryBlobSink, evaluate_request
    table = {"tg": density_table, "modulus": stress_table, "diffusion": msd_table}[kind]()
    path = tmp_path / ("density-temperature.csv" if kind == "tg" else "stress-strain.dat" if kind == "modulus" else "msd.dat")
    separator = "," if kind == "tg" else " "
    names = table.columns
    path.write_text(separator.join(names) + "\n" + "\n".join(separator.join(map(str, row))
                                                               for row in zip(*(table.column(n) for n in names))) + "\n")
    sink = MemoryBlobSink()
    parameters = {"time_min": 1000, "time_max": 10000} if kind == "diffusion" else {}
    result = evaluate_request({"preset": "lammps-"+kind, "parameters": parameters,
                               "outputs": ["summary", "fit", "diagnostics", "plot"]},
                              resolver=LocalDirResolver({"data": tmp_path}), blob_sink=sink, cache_dir=tmp_path / "cache")
    assert not result.get("errors"), result
    name, expected = {"tg": ("Tg", 340), "modulus": ("Modulus", 2.5), "diffusion": ("Diffusion", 1e-4)}[kind]
    assert result["outputs"]["summary"]["columns"][name][0] == pytest.approx(expected)
    assert result["outputs"]["plot"]["media_type"] == "image/svg+xml"
    assert result["outputs"]["diagnostics"]["type"] == "value"
    source = result["outputs"]["diagnostics"]["value"]["source"]["used"][0]
    assert source["path"] == path.name
    assert source["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert any(w["code"] == "md_fit_limits" for w in result["warnings"])
    assert result["outputs"]["fit"]["type"] == "table"


def test_missing_diffusion_window_is_not_automatically_fitted(tmp_path):
    from suan.graph.evaluator import EvaluationFailed
    from suan.graph.resolve import LocalDirResolver
    from suan.graph.service import MemoryBlobSink, evaluate_request
    (tmp_path / "msd.dat").write_text("Time MSD\n0 0\n1000 6\n2000 12\n3000 18\n")
    with pytest.raises(EvaluationFailed, match="Time minimum must be finite") as caught:
        evaluate_request({"preset": "lammps-diffusion", "outputs": ["summary"]},
                         resolver=LocalDirResolver({"data": tmp_path}), blob_sink=MemoryBlobSink(),
                         cache_dir=tmp_path / "cache")
    assert "summary" not in caught.value.partial.outputs


def test_mixed_units_in_a_restarted_log_are_not_relabelled_as_real():
    text = (Path(__file__).parent / "data/lammps/pet-npt.log").read_text()
    mixed = text.replace("units real", "units lj") + "\nclear\nunits real\n"
    for operation in (lambda: log_table(mixed, block=0), lambda: density_series({"mixed": mixed})):
        with pytest.raises(AnalysisError, match="throughout"):
            operation()


def test_lammps_log_source_records_the_frozen_source(tmp_path):
    from suan.graph.resolve import LocalDirResolver
    from suan.graph.service import MemoryBlobSink, evaluate_request
    path = tmp_path / "log.lammps"
    path.write_bytes((Path(__file__).parent / "data/lammps/pet-npt.log").read_bytes())
    graph = {"schema": "stk.graph/1", "catalog": {"stk": 1}, "parameters": [],
             "nodes": [{"id": "thermo", "type": "stk.source.lammps_log@1", "params": {"binding": "data"}}],
             "outputs": {"table": "thermo.out"}}
    result = evaluate_request({"graph": graph, "outputs": ["table"]}, resolver=LocalDirResolver({"data": tmp_path}),
                              blob_sink=MemoryBlobSink(), cache_dir=tmp_path / "cache")
    assert len(result["outputs"]["table"]["columns"]["Density"]) == 21
    assert result["outputs"]["table"]["units"]["Density"] == "g/cm3"
    source = result["outputs"]["table"]["attrs"]["source"]["used"][0]
    assert source["path"] == "log.lammps"
    assert source["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
