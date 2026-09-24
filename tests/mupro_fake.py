"""Fake MuPRO SDK for tests: muFerro-exact outputs without MPI or a licence.

Field value at 1-based (i, j, k, c) is i + 10*j + 100*k + 1000*c + step.
"""

from pathlib import Path
import json
import math
import os
import sys

STEMS = {"Charges": 1, "Displace": 3, "Eigen_St": 6, "Elas_For": 3, "Elast_En": 1, "Elast_St": 6,
         "Elec_For": 3, "Elec_Phi": 1, "Elect_En": 1, "Elefield": 3, "LandPFor": 3, "LandP_En": 1,
         "Strain": 6, "Stress": 6}
RECORDED = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "MUPROROOT", "SRUN_CPUS_PER_TASK", "STK_FAKE_MARK")


def write_case(case_dir, *, grid=(4, 3, 2), steps=3, interval=2, start=0):
    """input.toml/material.toml in the example's shape, including its mixed int/float array."""
    case_dir = Path(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "input.toml").write_text(
        "material = 'material.toml'\n\n[system]\n"
        f"simulation_grid = [{grid[0]}, {grid[1]}, {grid[2]}]\nlength_per_grid = [1, 1, 1]\n"
        "initial_polarization = [0.7, 0, 0]\npermittivity = [40, 40, 40]\ntemperature = 298\n"
        f"timestep_start = {start}\ntimestep_total = {steps}\ndt = 0.01\n\n"
        f"[normalizer]\np0 = 0.7\n\n[output]\ninterval = {interval}\n")
    (case_dir / "material.toml").write_text("[landau]\na1 = '3.8e5*(TEM-479)'\na11 = -7.3e7\n")


def _es(value):
    """Fortran es15.7e3, as muFerro's field DATs print values."""
    mantissa, exponent = f"{value:.7E}".split("E")
    return f"{mantissa}E{int(exponent):+04d}".rjust(15)


def _e18(value):
    """Fortran e18.10 (0.dddE+xx), as muFerro's energy rows print values (output.f90:104)."""
    if not math.isfinite(value):
        return "NaN".rjust(18)
    if value == 0:
        return "0.0000000000E+00".rjust(18)
    mantissa, exponent = f"{abs(value):.9E}".split("E")
    return f"{'-' if value < 0 else ''}0.{mantissa.replace('.', '')}E{int(exponent) + 1:+03d}".rjust(18)


def _frame(path, grid, components, step, scalar=False):
    """Header-first DAT as muFerro's mupro_output_4D/_3D write it (x slowest, component fastest)."""
    nx, ny, nz = grid
    rows = []
    for i in range(1, nx + 1):
        for j in range(1, ny + 1):
            for k in range(1, nz + 1):
                if scalar:
                    rows.append(f"{i:6d}{j:6d}{k:6d} {_es(i + 10*j + 100*k + 1000 + step)} ")
                else:
                    rows.extend(f"{i:6d}{j:6d}{k:6d}{c:6d} {_es(i + 10*j + 100*k + 1000*c + step)} "
                                for c in range(1, components + 1))
    header = "".join(f"{n:6d}" for n in (grid if scalar else (*grid, components)))
    path.write_text("\n".join([header.ljust(len(rows[0])), *rows]) + "\n")


def write_outputs(case_dir, *, grid=(4, 3, 2), steps=3, interval=2, start=0, mode="ok"):
    """Write what muFerro writes: 'ok', 'nan' (NaN total at the second step, then a stop
    without completion), 'missing_frame' (one expected frame absent) or 'fail' (stops
    after one step). The initial Polar frame is always step 0 (output.f90:24). Like
    muFerro, it appends to an existing energy_out.dat without a new header and to
    mupro_progress.jsonl (output.f90:31-43, 85-86), and replaces the completion file."""
    case_dir = Path(case_dir)
    header = not (case_dir / "energy_out.dat").exists()
    final = start + steps
    last = min({"nan": start + 2, "fail": start + 1}.get(mode, final), final)
    _frame(case_dir / "Polar.00000000.dat", grid, 3, 0)
    headers = ["Elastic Energy", "Electric Energy", "Landau Energy", "Gradient P Energy", "Total Energy"]
    energy = ["    " + "step".rjust(6) + " " * 9 + "".join(h.rjust(18) for h in headers)]
    progress = []
    for step in range(start + 1, last + 1):
        values = [1.5 * step, 0.25, -3.0 * step, 0.125, -1.125 * step]
        if mode == "nan" and step == last:
            values[4] = math.nan
        energy.append(f"kt: {step:6d} energy: " + "".join(_e18(v) for v in values))
        remainder = (step - start) % interval
        if remainder == 0:
            _frame(case_dir / f"Polar.{step:08d}.dat", grid, 3, step)
        if remainder == 1 or interval == 1:
            for stem, count in STEMS.items():
                if mode == "missing_frame" and stem == "Strain" and step == start + 1:
                    continue
                _frame(case_dir / f"{stem}.{step:08d}.dat", grid, count, step, scalar=count == 1)
        if mode == "nan" and step == last:
            break  # muFerro stops on a NaN total before that step's progress record (output.f90:187-192).
        progress.append(json.dumps({"step": step, "completed_steps": step - start, "total_steps": steps},
                                   separators=(",", ":")))
    with open(case_dir / "energy_out.dat", "a") as stream:
        stream.write("".join(line + "\n" for line in energy[0 if header else 1:]))
    with open(case_dir / "mupro_progress.jsonl", "a") as stream:
        stream.write("".join(line + "\n" for line in progress))
    if mode in {"ok", "missing_frame"}:
        (case_dir / "mupro_completion.json").write_text(
            f'{{"app":"muFerro","completed_steps":{steps},"final_step":{final}}}\n')


def read_toml(path, depth=0):
    """MuPRO's reader, written apart from STK's: `include` is a path or a list relative to
    the naming file, the including file and earlier includes win, sub-tables merge per key,
    at most 16 deep (muprosdk library/L0_Base/toml.f90:125-238)."""
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib

    def merge(destination, included):
        for key, value in included.items():
            if key not in destination:
                destination[key] = value
            elif isinstance(destination[key], dict) and isinstance(value, dict):
                merge(destination[key], value)

    data = tomllib.loads(Path(path).read_text())
    includes = data.pop("include", [])
    if includes and depth >= 16:
        raise ValueError("include nested more than 16 deep")
    for include in [includes] if isinstance(includes, str) else includes:
        merge(data, read_toml(Path(path).parent / include, depth + 1))
    return data


def fake_muferro(mode):
    """Body of the fake bin/muFerro: read ./input.toml and its material file like muFerro
    (input.f90:19-22) and write its outputs. A bad input aborts non-zero, as mupro_fatal does."""
    cwd = Path.cwd()
    (cwd / "fake-muferro.json").write_text(json.dumps(
        {"argv": sys.argv, "cwd": str(cwd), **{key: os.environ.get(key) for key in RECORDED}}))
    try:
        data = read_toml(cwd / "input.toml")
        read_toml(cwd / data["material"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"fake muFerro: input: {exc!r}", file=sys.stderr, flush=True)
        return 1
    system = data["system"]
    write_outputs(cwd, grid=tuple(system["simulation_grid"]), steps=system.get("timestep_total", 1000),
                  interval=data["output"]["interval"], start=system.get("timestep_start", 0), mode=mode)
    print("fake muFerro finished", flush=True)
    return 5 if mode == "fail" else 0


def _script(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{sys.executable}\n{body}")
    path.chmod(0o755)
    return path


def make_fake_sdk(root, *, grid=(4, 3, 2), steps=3, interval=2, mode="ok"):
    """An SDK prefix with bin/muFerro and the mupro-muferro example case."""
    root = Path(root)
    write_case(root / "share/mupro/skills/mupro-muferro/examples", grid=grid, steps=steps, interval=interval)
    _script(root / "bin" / "muFerro",
            f"import sys\nsys.path.insert(0, {str(Path(__file__).parent)!r})\n"
            f"from mupro_fake import fake_muferro\nsys.exit(fake_muferro({mode!r}))\n")
    return root


def make_fake_mpiexec(bin_dir):
    """mpiexec that drops '-n N' and execs the program once."""
    return _script(Path(bin_dir) / "mpiexec",
                   "import os, sys\nargs = sys.argv[1:]\nif args[:1] == ['-n']:\n    args = args[2:]\n"
                   "os.execv(args[0], args)\n")


def make_fake_srun(bin_dir):
    """srun that drops its --ntasks/--cpus-per-task flags and execs the program once."""
    return _script(Path(bin_dir) / "srun",
                   "import os, sys\nargs = [a for a in sys.argv[1:] if not a.startswith(('--ntasks=', "
                   "'--cpus-per-task='))]\nos.execv(args[0], args)\n")
