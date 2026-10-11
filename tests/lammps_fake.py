"""A fake LAMMPS for tests: reads the input script, takes -var values and writes log.lammps in LAMMPS's layout.

Not physics. Each ``run N`` (or ``minimize``) prints a thermo block (Step Temp Press Density PotEng) every
``thermo`` steps; Temp is the ``temperature`` variable and Density falls linearly with it (1.40 g/cm3 at 300 K,
-4e-4 per K). ``write_data FILE`` writes FILE. A JSON file next to the program sets a mode: ``nan`` (NaN in
the thermo output), ``error`` (an ERROR line, exit 1), ``unfinished`` (no Total wall time, exit 0), ``mpi``
(``-h`` reports MPICH instead of the MPI stubs), ``overwrite`` (rewrites system.data) and ``slow`` (sleeps 60 s).
"""
from pathlib import Path
import json
import sys

PROGRAM = '''#!{python}
import json, pathlib, re, sys
here = pathlib.Path(sys.argv[0])
config = here.with_suffix(".json")
mode = json.loads(config.read_text()).get("mode") if config.exists() else None
args = sys.argv[1:]
if "-h" in args:
    print("\\nLarge-scale Atomic/Molecular Massively Parallel Simulator - 2 Aug 2023 - Update 3\\n")
    print("MPI v4.1: MPICH Version: 4.1.2" if mode == "mpi" else "MPI v1.0: LAMMPS MPI STUBS for LAMMPS version 2 Aug 2023")
    print("\\nInstalled packages:\\n\\nKSPACE MANYBODY MOLECULE RIGID\\n")
    sys.exit(0)
variables, script, log = {{}}, None, "log.lammps"
index = 0
while index < len(args):
    if args[index] == "-in":
        script = args[index + 1]; index += 2
    elif args[index] == "-var":
        variables[args[index + 1]] = args[index + 2]; index += 3
    elif args[index] == "-log":
        log = args[index + 1]; index += 2
    else:
        index += 1
pathlib.Path("fake-lammps.json").write_text(json.dumps({{"argv": args}}))
out = ["LAMMPS (2 Aug 2023 - Update 3)"]
thermo, step = 0, 0
def value(name):
    return variables.get(name)
for raw in pathlib.Path(script).read_text().splitlines():
    line = raw.split("#")[0].strip()
    if not line:
        continue
    words = line.split()
    if words[0] == "variable" and len(words) > 3 and words[2] == "index":
        variables.setdefault(words[1], words[3])
        out.append(raw); continue
    line = re.sub(r"\\$\\{{(\\w+)\\}}", lambda m: variables[m.group(1)], line)
    words = line.split()
    out.append(line)
    if words[0] == "thermo":
        thermo = int(words[1])
    elif words[0] in ("run", "minimize"):
        steps = int(words[1]) if words[0] == "run" else 10
        every = thermo or steps
        temperature = float(value("temperature") or 300)
        density = 1.40 - 4e-4 * (temperature - 300)
        out.append("Per MPI rank memory allocation (min/avg/max) = 1.0 | 1.0 | 1.0 Mbytes")
        out.append("   Step          Temp          Press         Density         PotEng    ")
        for s in range(step, step + steps + 1, every):
            d = "nan" if mode == "nan" and s == step + steps else f"{{density:.6f}}"
            out.append(f"{{s:>10d}}   {{temperature:>12.4f}}   {{1.0:>12.4f}}   {{d:>12}}   {{-1000.0 - s * 0.01:>12.4f}}")
        if mode == "error":
            out.append("ERROR: Lost atoms: original 540 current 539 (src/thermo.cpp:494)")
            pathlib.Path(log).write_text("\\n".join(out) + "\\n")
            sys.exit(1)
        step += steps
        out.append(f"Loop time of 0.01 on 1 procs for {{steps}} steps with 540 atoms")
    elif words[0] == "write_data":
        pathlib.Path(words[1]).write_text("fake LAMMPS data file\\n")
if mode == "overwrite":
    pathlib.Path("system.data").write_text("changed by the run\\n")
if mode == "slow":
    import time
    time.sleep(60)
if mode != "unfinished":
    out.append("Total wall time: 0:00:01")
pathlib.Path(log).write_text("\\n".join(out) + "\\n")
'''

SCRIPT = """# STK test case: an NPT run whose temperature, steps and seed are set by STK
variable temperature index 300
variable steps index 100
variable seed index 4928459
units real
atom_style full
read_data system.data
velocity all create ${temperature} ${seed}
fix 1 all npt temp ${temperature} ${temperature} 100.0 iso ${pressure} ${pressure} 1000.0
thermo 20
run ${steps}
write_data final.data
"""


def make_fake_lammps(folder, mode=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    program = folder / "lmp"
    program.write_text(PROGRAM.format(python=sys.executable))
    program.chmod(0o755)
    set_mode(program, mode)
    return program


def set_mode(program, mode):
    Path(program).with_suffix(".json").write_text(json.dumps({"mode": mode}))


def write_case(folder, script=SCRIPT):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "in.npt").write_text(script)
    (folder / "system.data").write_text("fake data file\n\n2 atoms\n")
    return folder
