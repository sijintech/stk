"""Manual GMSO comparison. Historical PET charges are a fixture, not a decision.

Run with the molecular-modeling Python, PYTHONPATH=<repository>, and --out /tmp/...
Optionally --lammps /path/to/lmp checks run-0 component energies for both files.
Never runs a model endpoint. Output is public synthetic feasibility data only.
"""
import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import warnings

from build_pet import typed_structure
from suan.lammps.data import write_data
from suan.lammps.log import verify_log

SECTIONS = ("Masses", "Pair Coeffs", "Bond Coeffs", "Angle Coeffs", "Dihedral Coeffs",
            "Atoms", "Bonds", "Angles", "Dihedrals")


def read_data(path):
    sections, bounds, current = {}, {}, None
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line in SECTIONS:
            current = line
            sections[current] = {}
        elif current:
            words = line.split()
            sections[current][int(words[0])] = tuple(map(float, words[1:]))
        elif line.endswith(("xlo xhi", "ylo yhi", "zlo zhi", "xy xz yz")):
            words = line.split()
            n = 3 if words[-1] == "yz" else 2
            bounds[" ".join(words[n:])] = tuple(map(float, words[:n]))
    return sections, bounds


def close(a, b, tolerance):
    assert len(a) == len(b)
    assert all(math.isclose(x, y, rel_tol=0, abs_tol=tolerance) for x, y in zip(a, b)), (a, b)


def compare(reference, candidate):
    r, rb = read_data(reference)
    s, sb = read_data(candidate)
    assert rb.keys() == sb.keys()
    original_rb = dict(rb)
    xy, xz, yz = rb["xy xz yz"]
    if any((xy, xz, yz)):
        # GMSO 0.17.0 incorrectly writes dump bounding extents into a DATA
        # header. Undo that known error for the intended-cell comparison;
        # preserve the original header and verify the actual LAMMPS cell below.
        rb["xlo xhi"] = (rb["xlo xhi"][0] - min(0, xy, xz, xy+xz),
                         rb["xlo xhi"][1] - max(0, xy, xz, xy+xz))
        rb["ylo yhi"] = (rb["ylo yhi"][0] - min(0, yz), rb["ylo yhi"][1] - max(0, yz))
    for name in rb:
        # GMSO's box conversion rounds Angstrom lengths to three decimals.
        close(rb[name], sb[name], 5.1e-4)
    assert r["Atoms"].keys() == s["Atoms"].keys()
    rm, sm = {}, {}
    for index in r["Atoms"]:
        a, b = r["Atoms"][index], s["Atoms"][index]
        rm.setdefault(a[0], []).append(index)
        sm.setdefault(b[0], []).append(index)
        close(a[2:3], b[2:3], 5.1e-7)
        # GMSO's position conversion and its 8 significant digits reduce precision.
        close(a[3:], b[3:], 1.1e-5)
        close(r["Masses"][int(a[1])], s["Masses"][int(b[1])], 5.1e-4)
        close(r["Pair Coeffs"][int(a[1])], s["Pair Coeffs"][int(b[1])], 5.1e-6)
    # from_parmed labels all chains with the one default ParmEd residue here.
    # Check STK's molecule partition independently against the reference bonds.
    neighbours = {i: set() for i in r["Atoms"]}
    for row in r["Bonds"].values():
        i, j = map(int, row[1:])
        neighbours[i].add(j)
        neighbours[j].add(i)
    components, pending = [], set(neighbours)
    while pending:
        component, frontier = set(), {min(pending)}
        while frontier:
            component.update(frontier)
            frontier = set().union(*(neighbours[i] for i in frontier)) - component
        pending -= component
        components.append(sorted(component))
    assert sorted(components) == sorted(sm.values())
    for section, coefficients in (("Bonds", "Bond Coeffs"), ("Angles", "Angle Coeffs"),
                                  ("Dihedrals", "Dihedral Coeffs")):
        def terms(data):
            out = {}
            for row in data[section].values():
                members = tuple(map(int, row[1:]))
                key = min(members, members[::-1])
                assert key not in out, (section, key)
                out[key] = data[coefficients][int(row[0])]
            return out
        rt, st = terms(r), terms(s)
        assert rt.keys() == st.keys(), section
        for key in rt:
            close(rt[key], st[key], 5.1e-7)
        # Compare the physical type partition even when STK merges aliases.
        assert Counter(tuple(round(v, 6) for v in values) for values in rt.values()) == Counter(
            tuple(round(v, 6) for v in values) for values in st.values())
    return {"atoms": len(s["Atoms"]), "molecules": len(sm), "gmso_residue_molecules": len(rm),
            "gmso_triclinic_header_bug": any((xy, xz, yz)), "gmso_raw_box": original_rb, "stk_box": sb,
            "topology": {name: len(s[name]) for name in ("Bonds", "Angles", "Dihedrals")},
            "reference_types": {name: len(r[name]) for name in SECTIONS[:5]},
            "stk_types": {name: len(s[name]) for name in SECTIONS[:5]}}


def energies(program, data, geometry=None):
    if geometry is not None:
        # Isolate potential conversion from GMSO's coordinate/box rounding.
        # A loosely packed initial box can have enormous forces at overlaps.
        canonical, bounds = read_data(geometry)
        lines, atoms_section = [], False
        for line in data.read_text().splitlines():
            plain = line.split("#", 1)[0].strip()
            if plain in SECTIONS:
                atoms_section = plain == "Atoms"
            elif atoms_section and plain:
                row = plain.split()
                xyz = canonical["Atoms"][int(row[0])][3:]
                line = " ".join(row[:4] + [format(v, ".16g") for v in xyz])
            elif any(plain.endswith(name) for name in bounds):
                name = next(name for name in bounds if plain.endswith(name))
                line = " ".join(format(v, ".16g") for v in bounds[name]) + " " + name
            lines.append(line)
        normalized = data.with_name(data.stem + "-same-geometry.data")
        normalized.write_text("\n".join(lines) + "\n")
        data = normalized
    script = data.with_suffix(".in")
    script.write_text(f"""units real
atom_style full
boundary p p p
pair_style lj/cut/coul/long 9.0
pair_modify mix geometric
bond_style harmonic
angle_style harmonic
dihedral_style opls
special_bonds lj/coul 0 0 0.5
read_data {data.name}
kspace_style pppm 1e-6
thermo_style custom step pe ebond eangle edihed evdwl ecoul elong
thermo_modify format float %.15g
run 0
""")
    log = data.with_suffix(".log")
    result = subprocess.run([program, "-in", script.name, "-log", log.name, "-nocite"], cwd=data.parent,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
    report = verify_log(log.read_text(), result.returncode)
    assert report["verification"]["status"] == "passed", (report, result.stdout[-1000:])
    return report["qoi"]["final"]


def actual_cell(program, data):
    script = data.with_suffix(".cell.in")
    script.write_text(f"units real\natom_style full\nread_data {data.name} nocoeff\n"
                      'print "STK_CELL $(lx:%.15g) $(ly:%.15g) $(lz:%.15g) $(xy:%.15g) $(xz:%.15g) $(yz:%.15g) $(vol:%.15g) '
                      '$(cella:%.15g) $(cellb:%.15g) $(cellc:%.15g) $(cellalpha:%.15g) $(cellbeta:%.15g) $(cellgamma:%.15g)"\n')
    result = subprocess.run([program, "-in", script.name, "-log", "none", "-nocite"], cwd=data.parent,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout[-1000:]
    values = next(line.split()[1:] for line in result.stdout.splitlines() if line.startswith("STK_CELL "))
    return dict(zip(("lx", "ly", "lz", "xy", "xz", "yz", "volume", "a", "b", "c", "alpha", "beta", "gamma"),
                    map(float, values)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--lammps")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]
    warnings.filterwarnings("ignore")
    from gmso.external import from_parmed
    from gmso.formats.lammpsdata import write_lammpsdata
    structure, timings = typed_structure()
    reports = {"fixture": "540-atom PET; historical 0.0 charge patch UNDECIDED; not material validation",
               "preparation_seconds": timings}
    for name, angles in (("orthogonal", [90, 90, 90]), ("triclinic", [80, 85, 75])):
        structure.box = list(structure.box[:3]) + angles
        reference, candidate = args.out / f"{name}-gmso.data", args.out / f"{name}-stk.data"
        t = time.perf_counter()
        topology = from_parmed(structure)
        converted = time.perf_counter() - t
        t = time.perf_counter()
        write_lammpsdata(topology, str(reference), atom_style="full", unit_style="real")
        gmso_time = time.perf_counter() - t
        t = time.perf_counter()
        write_data(structure, candidate, allow_untyped_impropers=True)
        stk_time = time.perf_counter() - t
        report = compare(reference, candidate)
        report.update(gmso_conversion_seconds=converted, gmso_write_seconds=gmso_time, stk_write_seconds=stk_time)
        if args.lammps:
            gc, sc = actual_cell(args.lammps, reference), actual_cell(args.lammps, candidate)
            close([sc[key] for key in ("a", "b", "c", "alpha", "beta", "gamma")], structure.box, 1e-10)
            report.update(gmso_actual_cell=gc, stk_actual_cell=sc)
            re, se = energies(args.lammps, reference, candidate), energies(args.lammps, candidate)
            for column in re:
                assert math.isclose(re[column], se[column], rel_tol=1e-9, abs_tol=0.002), (column, re, se)
            report.update(energy_geometry="STK coordinates and cell for both files (isolate coefficients)",
                          gmso_energy=re, stk_energy=se)
        reports[name] = report
        print(json.dumps({name: report}, ensure_ascii=False), flush=True)
    (args.out / "comparison.json").write_text(json.dumps(reports, indent=2) + "\n")


if __name__ == "__main__":
    main()
