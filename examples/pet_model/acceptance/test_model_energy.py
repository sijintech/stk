"""Independent optional PET chemistry and real-engine acceptance.

Run with molecular-modeling Python, pytest available, repository on PYTHONPATH,
STK_PACKMOL and STK_LAMMPS pointing to their real executables. Expected charges,
LJ and bonded coefficients below were transcribed independently from Tables
S1–S4 (doi:10.3390/polym14061161) and GROMACS v2025.3 OPLS fallback entries.
No expected physical values are taken from the worker's profile or validation.

The OpenMM comparison is explicitly NONPERIODIC, all-to-all direct Coulomb/LJ,
with the same OPLS special pairs. The generated periodic PPPM case is separately
read by real LAMMPS. These Hamiltonians are not compared as if interchangeable.
Packed-state energy is checked unchanged. Strict forces use a separately
recorded tiny coordinate perturbation to avoid LAMMPS's near-planar sine guard.
Neither check is a converged PET property or amorphous-state validation.
"""
from collections import Counter
import hashlib
from itertools import combinations
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys

import pytest


# Role: charge e, sigma A, epsilon kcal/mol, mass amu, bonded class.
ATOMS = {
    "CA": (-.115, 3.550, .070, 12.012, "CA"),
    "HA": (.115, 2.420, .030, 1.008, "HA"),
    "COa": (.635, 3.750, .066, 12.012, "CO"),
    "COe": (.625, 3.750, .066, 12.012, "CO"),
    "Oa": (-.440, 2.960, .210, 15.999, "O"),
    "Oe": (-.430, 2.960, .210, 15.999, "O"),
    "OES": (-.330, 2.900, .140, 15.999, "OES"),
    "CTe": (.190, 3.500, .066, 12.012, "CT"),
    "CTt": (.145, 3.500, .066, 12.012, "CT"),
    "HAE": (.030, 2.420, .030, 1.008, "HAE"),
    "HC": (.060, 2.500, .030, 1.008, "HC"),
    "OHa": (-.530, 3.000, .170, 15.999, "OH"),
    "HOa": (.450, .500, .030, 1.008, "HO"),
    # Explicit STK correction of the published -0.566 terminal-O rounding.
    "OHt": (-.565, 3.000, .170, 15.999, "OH"),
    "HOt": (.300, .500, .030, 1.008, "HO"),
}


def _canonical(values):
    values = tuple(values)
    return min(values, values[::-1])


def _table(entries):
    return {_canonical(key.split()): tuple(value) for key, value in entries.items()}


# LAMMPS K includes the harmonic 1/2; values are kcal/mol/A2 and kcal/mol/rad2.
BONDS = _table({
    "HO OH": (553, .945), "OH CO": (450, 1.364), "CO O": (570, 1.229),
    "CO CA": (400, 1.490), "CA CA": (469, 1.400), "CA HA": (367, 1.080),
    "CO OES": (214, 1.327), "OES CT": (320, 1.410), "CT CT": (268, 1.529),
    "CT HAE": (340, 1.090), "CT HC": (340, 1.090), "CT OH": (320, 1.410),
})
ANGLES = _table({
    "HO OH CO": (35, 113), "OH CO O": (100, 123.32), "OH CO CA": (85, 111.88),
    "O CO CA": (80, 120.4), "CO CA CA": (85, 120), "CA CA HA": (35, 120),
    "CA CO OES": (81, 111.4), "O CO OES": (83, 123.4), "CO OES CT": (83, 116.9),
    "OES CT HAE": (35, 109.5), "CT CT HAE": (37.5, 110.7), "OES CT CT": (50, 109.5),
    "HC CT HC": (33, 107.8), "CA CA CA": (63, 120), "CT CT HC": (37.5, 110.7),
    "CT CT OH": (50, 109.5), "CT OH HO": (55, 108.5), "HAE CT HAE": (33, 107.8),
    "HC CT OH": (35, 109.5),
})
# Published Fourier coefficients, kcal/mol, preserving the source 1/2 formula.
FOURIER = _table({
    "HO OH CO O": (1.844, 7.482, 0, 0), "OH CO CA CA": (0, .720, 0, 0),
    "CO CA CA HA": (0, 7.250, 0, 0), "CO CA CA CA": (0, 7.250, 0, 0),
    "CA CA CA CA": (0, 7.250, 0, 0), "CA CA CA HA": (0, 7.250, 0, 0),
    "CA CA CO O": (0, 2.100, 0, 0), "CA CA CO OES": (0, 1.975, 0, 0),
    "CA CO OES CT": (1.199, 6.497, 0, 0), "O CO OES CT": (0, 6.000, 0, 0),
    "CO OES CT CT": (-.518, -.940, .235, 0), "CO OES CT HAE": (0, 0, .161, 0),
    "OES CT CT HAE": (0, 0, .468, 0), "HAE CT CT HAE": (0, 0, .300, 0),
    "CT CT OH HO": (4.515, -3.854, 0, 0), "HC CT OH HO": (0, 0, .389, 0),
})
# Canonical GROMACS RB coefficients in their ORIGINAL kJ/mol units; explicitly
# expand its X-CA-CA-X wildcard and bonded-only CO/C, OES/OS and HAE/HC aliases.
RB_KJ = _table({
    "CA CO OH HO": (29.28800, -8.36800, -20.92000, 0, 0, 0),
    "HA CA CA HA": (30.33400, 0, -30.33400, 0, 0, 0),
    "HAE CT CT HC": (.62760, 1.88280, 0, -2.51040, 0, 0),
    "HAE CT CT OH": (.97905, 2.93716, 0, -3.91622, 0, 0),
    "HC CT CT OES": (.97905, 2.93716, 0, -3.91622, 0, 0),
    "OES CT CT OES": (-1.15060, 1.15060, 0, 0, 0, 0),
    "OES CT CT OH": (9.03534, -9.03534, 0, 0, 0, 0),
})
SECTIONS = ("Masses", "Pair Coeffs", "Bond Coeffs", "Angle Coeffs", "Dihedral Coeffs",
            "Improper Coeffs", "Atoms", "Bonds", "Angles", "Dihedrals", "Impropers")


def _read_data(path):
    sections, current = {}, None
    for line in path.read_text().splitlines():
        words = line.split("#", 1)[0].strip()
        if words in SECTIONS:
            current = words
            sections[current] = {}
        elif current and words:
            row = words.split()
            identifier = int(row[0])
            assert identifier not in sections[current]
            sections[current][identifier] = tuple(map(float, row[1:]))
    assert set(sections) == set(SECTIONS)
    return sections


def _chemistry(data, length, count):
    atoms = data["Atoms"]
    assert set(atoms) == set(range(1, (22 * length + 3) * count + 1))
    elements = {}
    for identifier, atom in atoms.items():
        mass = data["Masses"][int(atom[1])][0]
        choices = [z for z, expected in ((1, 1.008), (6, 12.012), (8, 15.999)) if abs(mass - expected) < 1e-9]
        assert len(choices) == 1
        elements[identifier] = choices[0]
    assert Counter(elements.values()) == {1: (8 * length + 2) * count, 6: 10 * length * count,
                                         8: (4 * length + 1) * count}
    graph = {identifier: set() for identifier in atoms}
    for row in data["Bonds"].values():
        i, j = map(int, row[1:])
        assert i != j and j not in graph[i]
        graph[i].add(j)
        graph[j].add(i)
    assert all(len(graph[i]) == 1 for i in atoms if elements[i] == 1)
    assert all(len(graph[i]) in (1, 2) for i in atoms if elements[i] == 8)
    roles = {}
    # Chemical environments, rather than manifest names, determine each type.
    for i in atoms:
        if elements[i] != 6:
            continue
        neighbors = Counter(elements[j] for j in graph[i])
        if neighbors == {8: 2, 6: 1}:
            acid = any(any(elements[k] == 1 for k in graph[j]) for j in graph[i] if elements[j] == 8)
            roles[i] = "COa" if acid else "COe"
        elif neighbors in ({6: 2, 1: 1}, {6: 3}):
            roles[i] = "CA"
        elif neighbors == {1: 2, 6: 1, 8: 1}:
            alcohol = any(any(elements[k] == 1 for k in graph[j]) for j in graph[i] if elements[j] == 8)
            roles[i] = "CTt" if alcohol else "CTe"
        else:
            raise AssertionError((i, neighbors))
    for i in atoms:
        if elements[i] == 8:
            neighbors = [j for j in graph[i] if elements[j] == 6]
            if len(graph[i]) == 1:
                roles[i] = "Oa" if roles[neighbors[0]] == "COa" else "Oe"
            elif len(neighbors) == 1:
                roles[i] = "OHa" if roles[neighbors[0]] == "COa" else "OHt"
            else:
                assert Counter(roles[j] for j in neighbors) == {"COe": 1, "CTe": 1}
                roles[i] = "OES"
    for i in atoms:
        if elements[i] == 1:
            neighbor, = graph[i]
            roles[i] = {"CA": "HA", "CTe": "HAE", "CTt": "HC", "OHa": "HOa", "OHt": "HOt"}[roles[neighbor]]
    groups, remaining = [], set(atoms)
    while remaining:
        component, frontier = set(), {min(remaining)}
        while frontier:
            component.update(frontier)
            frontier = set().union(*(graph[i] for i in frontier)) - component
        groups.append(component)
        remaining -= component
    assert len(groups) == count
    expected = {"CA": 6 * length, "HA": 4 * length, "COe": 2 * length - 1,
                "Oe": 2 * length - 1, "OES": 2 * length - 1, "CTe": 2 * length - 1,
                "HAE": 4 * length - 2, "COa": 1, "Oa": 1, "OHa": 1, "HOa": 1,
                "CTt": 1, "HC": 2, "OHt": 1, "HOt": 1}
    molecule_ids = []
    for group in groups:
        assert Counter(roles[i] for i in group) == expected
        molecule, = {int(atoms[i][0]) for i in group}
        molecule_ids.append(molecule)
        assert abs(math.fsum(atoms[i][2] for i in group)) < 1e-10
        # Verify each isolated benzene ring and its para substituents.
        ring_remaining = {i for i in group if roles[i] == "CA"}
        rings = []
        while ring_remaining:
            ring, frontier = set(), {min(ring_remaining)}
            while frontier:
                ring.update(frontier)
                frontier = {j for i in frontier for j in graph[i] if roles[j] == "CA"} - ring
            assert len(ring) == 6
            assert all(len(graph[i] & ring) == 2 for i in ring)
            ipso = [i for i in ring if any(roles[j] in ("COa", "COe") for j in graph[i])]
            assert len(ipso) == 2
            reached, frontier = {ipso[0]}, {ipso[0]}
            for distance in range(1, 4):
                frontier = {j for i in frontier for j in graph[i] & ring} - reached
                if ipso[1] in frontier:
                    assert distance == 3
                    break
                reached.update(frontier)
            else:
                raise AssertionError("ring carbonyls must be para")
            rings.append(ring)
            ring_remaining -= ring
        assert len(rings) == length
    assert len(set(molecule_ids)) == count
    for i, role in roles.items():
        charge, sigma, epsilon, mass, _ = ATOMS[role]
        numeric_type = int(atoms[i][1])
        assert atoms[i][2] == pytest.approx(charge, abs=1e-10)
        assert data["Pair Coeffs"][numeric_type] == pytest.approx((epsilon, sigma), abs=1e-10)
        assert data["Masses"][numeric_type][0] == pytest.approx(mass, abs=1e-10)
    return roles, graph


def _topology(data, roles, graph, length, count):
    expected = {"Bonds": {_canonical((i, j)) for i in graph for j in graph[i]},
                "Angles": {_canonical((i, center, j)) for center, neighbors in graph.items()
                           for i, j in combinations(sorted(neighbors), 2)},
                "Dihedrals": {_canonical((i, j, k, l)) for j in graph for k in graph[j] if j < k
                              for i in graph[j] - {k} for l in graph[k] - {j} if i != l}}
    assert {name: len(terms) for name, terms in expected.items()} == {
        "Bonds": (23 * length + 2) * count, "Angles": (38 * length + 1) * count,
        "Dihedrals": 51 * length * count}
    for section, keys in expected.items():
        actual = [_canonical(map(int, row[1:])) for row in data[section].values()]
        assert len(actual) == len(set(actual)) and set(actual) == keys
    def classes(members):
        return _canonical(ATOMS[roles[i]][4] for i in members)
    for section, coefficients, reference in (("Bonds", "Bond Coeffs", BONDS), ("Angles", "Angle Coeffs", ANGLES)):
        for row in data[section].values():
            members = tuple(map(int, row[1:]))
            assert data[coefficients][int(row[0])] == pytest.approx(reference[classes(members)], abs=1e-8)
    offset = 0.0
    for row in data["Dihedrals"].values():
        key = classes(tuple(map(int, row[1:])))
        if key in FOURIER:
            expected_coefficients = FOURIER[key]
        else:
            c = [v / 4.184 for v in RB_KJ[key]]
            # Independently check the algebraic Fourier coefficients; the
            # OpenMM energy below uses the SOURCE RB equation, not this result.
            expected_coefficients = (-2 * c[1] - 1.5 * c[3], -c[2] - c[4], -.5 * c[3], -.25 * c[4])
            offset += math.fsum(c)
        assert data["Dihedral Coeffs"][int(row[0])] == pytest.approx(expected_coefficients, abs=1e-8)
    wanted = {}
    for center, neighbors in graph.items():
        if roles[center] in ("COa", "COe"):
            oxygen, = (i for i in neighbors if roles[i] in ("Oa", "Oe"))
            aryl, = (i for i in neighbors if roles[i] == "CA")
            bridge, = (i for i in neighbors if roles[i] in ("OHa", "OES"))
            wanted[(oxygen, center, aryl, bridge)] = (10.5, -1, 2)
        elif roles[center] == "CA":
            rings = sorted(i for i in neighbors if roles[i] == "CA")
            external, = (i for i in neighbors if roles[i] != "CA")
            wanted[(external, center, *rings)] = (1.1, -1, 2)
    actual = {tuple(map(int, row[1:])): data["Improper Coeffs"][int(row[0])]
              for row in data["Impropers"].values()}
    assert len(actual) == len(data["Impropers"]) == 8 * length * count
    assert actual == wanted
    return expected, wanted, offset


def _reference_system(data, roles, graph, topology, impropers):
    import openmm as mm
    system = mm.System()
    for i in data["Atoms"]:
        system.addParticle(ATOMS[roles[i]][3])
    bond, angle = mm.HarmonicBondForce(), mm.HarmonicAngleForce()
    fourier = mm.CustomTorsionForce("(a1*(1+cos(theta))+a2*(1-cos(2*theta))+a3*(1+cos(3*theta))+a4*(1-cos(4*theta)))/2")
    for key in ("a1", "a2", "a3", "a4"):
        fourier.addPerTorsionParameter(key)
    rb = mm.CustomTorsionForce("c0+c1*cos(theta-pi)+c2*cos(theta-pi)^2+c3*cos(theta-pi)^3+c4*cos(theta-pi)^4+c5*cos(theta-pi)^5;pi=3.141592653589793")
    for key in ("c0", "c1", "c2", "c3", "c4", "c5"):
        rb.addPerTorsionParameter(key)
    improper = mm.PeriodicTorsionForce()
    def classes(members):
        return _canonical(ATOMS[roles[i]][4] for i in members)
    for i, j in sorted(topology["Bonds"]):
        k, length = BONDS[classes((i, j))]
        bond.addBond(i - 1, j - 1, length * .1, k * 2 * 4.184 * 100)
    for i, j, k in sorted(topology["Angles"]):
        amplitude, degrees = ANGLES[classes((i, j, k))]
        angle.addAngle(i - 1, j - 1, k - 1, math.radians(degrees), amplitude * 2 * 4.184)
    for members in sorted(topology["Dihedrals"]):
        key = classes(members)
        if key in FOURIER:
            fourier.addTorsion(*(i - 1 for i in members), [v * 4.184 for v in FOURIER[key]])
        else:
            rb.addTorsion(*(i - 1 for i in members), RB_KJ[key])
    for members, (amplitude, _, _) in impropers.items():
        improper.addTorsion(*(i - 1 for i in members), 2, math.pi, amplitude * 4.184)
    # Match the documented LAMMPS 'real' conversion constant explicitly, rather
    # than hiding its small difference from OpenMM's built-in Coulomb constant.
    # https://raw.githubusercontent.com/lammps/lammps/stable_22Jul2025/src/force.cpp
    coulomb = 332.06371 * 4.184 * .1  # kcal A -> kJ nm
    lj = mm.CustomNonbondedForce("4*sqrt(e1*e2)*((sqrt(s1*s2)/r)^12-(sqrt(s1*s2)/r)^6)")
    lj.addPerParticleParameter("s")
    lj.addPerParticleParameter("e")
    electrostatic = mm.CustomNonbondedForce(f"{coulomb:.17g}*q1*q2/r")
    electrostatic.addPerParticleParameter("q")
    lj14 = mm.CustomBondForce("2*e*((s/r)^12-(s/r)^6)")
    lj14.addPerBondParameter("s")
    lj14.addPerBondParameter("e")
    coul14 = mm.CustomBondForce(f"{coulomb / 2:.17g}*qq/r")
    coul14.addPerBondParameter("qq")
    for i in data["Atoms"]:
        charge, sigma, epsilon, _, _ = ATOMS[roles[i]]
        lj.addParticle([sigma * .1, epsilon * 4.184])
        electrostatic.addParticle([charge])
    for i in graph:
        seen, frontier = {i}, {i}
        for distance in range(1, 4):
            frontier = {j for k in frontier for j in graph[k]} - seen
            seen.update(frontier)
            for j in sorted(frontier):
                if i >= j:
                    continue
                lj.addExclusion(i - 1, j - 1)
                electrostatic.addExclusion(i - 1, j - 1)
                if distance == 3:
                    qa, sa, ea, _, _ = ATOMS[roles[i]]
                    qb, sb, eb, _, _ = ATOMS[roles[j]]
                    lj14.addBond(i - 1, j - 1, [math.sqrt(sa * sb) * .1, math.sqrt(ea * eb) * 4.184])
                    coul14.addBond(i - 1, j - 1, [qa * qb])
    for group, forces in enumerate(((bond,), (angle,), (fourier, rb), (improper,), (lj, lj14), (electrostatic, coul14))):
        for force in forces:
            force.setForceGroup(group)
            system.addForce(force)
    return system


def _lammps(program, directory, periodic=False):
    prefix = "units real\natom_style full\n"
    if periodic:
        script = prefix + "boundary p p p\ninclude model.in\n"
    else:
        # Original unwrapped positions can be slightly beyond the packed box.
        # Only the NONPERIODIC reference bounds are expanded; coordinates and
        # coefficients stay identical, and the generated periodic case is intact.
        path = directory / "pet.data"
        positions = list(_read_data(path)["Atoms"].values())
        lines = []
        for line in path.read_text().splitlines():
            words = line.split()
            for axis, index in zip("xyz", (3, 4, 5)):
                if len(words) == 4 and words[2:] == [axis + "lo", axis + "hi"]:
                    low = min(float(words[0]), min(p[index] for p in positions) - 1)
                    high = max(float(words[1]), max(p[index] for p in positions) + 1)
                    line = f"{low:.16g} {high:.16g} {axis}lo {axis}hi"
            lines.append(line)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        script = (prefix + "boundary f f f\npair_style lj/cut/coul/cut 1000.0\n"
                  "pair_modify mix geometric tail no shift no\nbond_style harmonic\nangle_style harmonic\n"
                  "dihedral_style opls\nimproper_style cvff\nspecial_bonds lj/coul 0 0 0.5\n"
                  "read_data pet.data\nneighbor 2.0 nsq\n")
    script += ("thermo_style custom step pe ebond eangle edihed eimp evdwl ecoul elong\n"
               "thermo_modify format float %.16g\nrun 0\n"
               "write_dump all custom forces.dat id fx fy fz modify sort id format float %.16g\n")
    (directory / "check.in").write_text(script, encoding="utf-8")
    result = subprocess.run([program, "-in", "check.in", "-log", "log.lammps", "-nocite"],
                            cwd=directory, capture_output=True, text=True, timeout=120)
    (directory / "screen.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr
    assert "Total wall time:" in result.stdout and "ERROR" not in result.stdout
    row = next(line.split() for line in result.stdout.splitlines() if len(line.split()) == 9 and line.split()[0] == "0")
    energies = dict(zip(("pe", "ebond", "eangle", "edihed", "eimp", "evdwl", "ecoul", "elong"), map(float, row[1:])))
    lines = (directory / "forces.dat").read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("ITEM: ATOMS")) + 1
    forces = [list(map(float, line.split()[1:])) for line in lines[start:]]
    assert all(math.isfinite(v) for v in energies.values())
    assert all(math.isfinite(v) for row in forces for v in row)
    return energies, forces


def _controlled_positions(original_A, torsions):
    """Avoid the engine's documented 1e-5 sine guard without weakening a check.

LAMMPS dihedral_opls.cpp limits sin(phi)'s denominator at almost planar
torsions. Keep the packed-state energies/force discrepancy as evidence, and
separately compare exact forces at a reproducible slightly perturbed geometry.
"""
    generator = random.Random(8703)
    def cross(a, b):
        return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    def norm(a):
        return math.sqrt(sum(v * v for v in a))
    def sine(points, members):
        a, b, c, d = (points[i - 1] for i in members)
        ab = [x - y for x, y in zip(a, b)]
        cb = [x - y for x, y in zip(c, b)]
        dc = [x - y for x, y in zip(d, c)]
        n1, n2 = cross(ab, cb), cross([-v for v in cb], dc)
        return norm(cross(n1, n2)) / (norm(n1) * norm(n2))
    for attempt in range(64):
        positions = [[v + generator.uniform(-.01, .01) for v in point] for point in original_A]
        minimum = min(sine(positions, members) for members in torsions)
        if minimum > 2e-5:
            return positions, {"seed": 8703, "attempt": attempt, "maximum_coordinate_change_A": .01,
                               "minimum_abs_sin_proper_phi": minimum}
    raise AssertionError("no controlled geometry clear of the near-planar torsion guard")


def _write_positions(path, positions_A):
    current, lines = None, []
    for line in path.read_text().splitlines():
        plain = line.split("#", 1)[0].strip()
        if plain in SECTIONS:
            current = plain
        elif current == "Atoms" and plain:
            words = line.split()
            identifier = int(words[0])
            line = " ".join(words[:4] + [format(v, ".16g") for v in positions_A[identifier - 1]])
        lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.parametrize("length,count,density", [(2, 1, 80.0), (4, 6, 250.0)], ids=["one-DP2", "six-DP4"])
def test_independent_pet_model(length, count, density, tmp_path):
    packmol, lammps = os.environ.get("STK_PACKMOL"), os.environ.get("STK_LAMMPS")
    assert packmol and lammps, "set STK_PACKMOL and STK_LAMMPS to real executables"
    import openmm as mm
    from openmm import unit
    repository = Path(__file__).resolve().parents[3]
    parameters = {"chain_length": length, "chain_count": count, "packing_density": density, "seed": 4928459}
    config = tmp_path / "parameters.json"
    config.write_text(json.dumps(parameters), encoding="utf-8")
    case = tmp_path / "case"
    bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('suan.lammps.pet_worker',run_name='__main__')"
    worker = subprocess.run([sys.executable, "-I", "-c", bootstrap, str(repository), "--parameters", str(config),
                             "--out", str(case), "--packmol", packmol], cwd=tmp_path,
                            env={"PATH": os.defpath, "STK_TOKEN_PLAN_API_KEY": ""}, capture_output=True, text=True, timeout=600)
    (tmp_path / "worker-screen.txt").write_text(worker.stdout + worker.stderr, encoding="utf-8")
    assert worker.returncode == 0, worker.stdout[-4000:] + worker.stderr[-4000:]
    assert {p.name for p in case.iterdir()} == {"pet.data", "model.in", "forcefield.xml", "pet-model.json",
                                               "in.pet", "in.tg", "in.modulus", "in.diffusion"}
    manifest = json.loads((case / "pet-model.json").read_text())
    assert manifest["format"] == "stk.pet-model/1" and manifest["parameters"] == parameters
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((case / name).read_bytes()).hexdigest() == digest
    assert hashlib.sha256((case / "forcefield.xml").read_bytes()).hexdigest() == manifest["forcefield_xml_sha256"]
    data = _read_data(case / "pet.data")
    roles, graph = _chemistry(data, length, count)
    topology, impropers, offset = _topology(data, roles, graph, length, count)
    direct = tmp_path / "direct"
    periodic = tmp_path / "periodic"
    direct.mkdir()
    periodic.mkdir()
    for folder in (direct, periodic):
        shutil.copyfile(case / "pet.data", folder / "pet.data")
        shutil.copyfile(case / "model.in", folder / "model.in")
    packed_measured, packed_lammps_forces = _lammps(lammps, direct)
    periodic_energies, _ = _lammps(lammps, periodic, periodic=True)
    system = _reference_system(data, roles, graph, topology, impropers)
    integrator = mm.VerletIntegrator(.001)
    context = mm.Context(system, integrator, mm.Platform.getPlatformByName("Reference"))
    original_A = [list(row[3:]) for row in data["Atoms"].values()]
    context.setPositions([[v * .1 for v in point] for point in original_A])
    names = ("ebond", "eangle", "edihed", "eimp", "evdwl", "ecoul")
    def component_energies():
        result = {name: context.getState(getEnergy=True, groups={group}).getPotentialEnergy().value_in_unit(unit.kilocalorie_per_mole)
                  for group, name in enumerate(names)}
        result["edihed"] -= offset
        return result
    packed_reference = component_energies()
    for name in names:
        assert packed_measured[name] == pytest.approx(packed_reference[name], rel=1e-10, abs=1e-7)
    packed_reference_forces = [[float(v) for v in row] for row in context.getState(getForces=True).getForces(asNumpy=True)
                               .value_in_unit(unit.kilocalorie_per_mole / unit.angstrom)]
    packed_force_discrepancy = max(abs(a - b) for x, y in zip(packed_lammps_forces, packed_reference_forces) for a, b in zip(x, y))
    controlled_A, controlled_metadata = _controlled_positions(original_A, topology["Dihedrals"])
    controlled = tmp_path / "controlled"
    controlled.mkdir()
    shutil.copyfile(case / "pet.data", controlled / "pet.data")
    _write_positions(controlled / "pet.data", controlled_A)
    measured, lammps_forces = _lammps(lammps, controlled)
    positions = [[v * .1 for v in point] for point in controlled_A]
    context.setPositions(positions)
    reference = component_energies()
    for name in names:
        assert measured[name] == pytest.approx(reference[name], rel=1e-10, abs=1e-7), (name, measured, reference)
    assert measured["pe"] == pytest.approx(sum(reference.values()), rel=1e-10, abs=1e-7)
    reference_forces = [[float(v) for v in row] for row in context.getState(getForces=True).getForces(asNumpy=True)
                        .value_in_unit(unit.kilocalorie_per_mole / unit.angstrom)]
    assert len(lammps_forces) == len(reference_forces) == (22 * length + 3) * count
    for actual, expected in zip(lammps_forces, reference_forces):
        assert actual == pytest.approx(expected, rel=1e-8, abs=1e-6)
    sampled = [next(i for i, role in roles.items() if role == wanted) for wanted in ("CA", "COe", "OES", "OHt")]
    differences = []
    step_A = 1e-5
    for identifier in sampled:
        for axis in range(3):
            high, low = [row[:] for row in positions], [row[:] for row in positions]
            high[identifier - 1][axis] += step_A * .1
            low[identifier - 1][axis] -= step_A * .1
            context.setPositions(high)
            up = context.getState(getEnergy=True).getPotentialEnergy().value_in_unit(unit.kilocalorie_per_mole)
            context.setPositions(low)
            down = context.getState(getEnergy=True).getPotentialEnergy().value_in_unit(unit.kilocalorie_per_mole)
            force = -(up - down) / (2 * step_A)
            difference = abs(force - lammps_forces[identifier - 1][axis])
            differences.append(difference)
            assert force == pytest.approx(lammps_forces[identifier - 1][axis], rel=1e-6, abs=1e-4)
    report = {"parameters": parameters, "scope": "independent chemistry/parameter and run0 equivalence; no material property validation",
              "atoms": len(data["Atoms"]), "bonds": len(topology["Bonds"]), "angles": len(topology["Angles"]),
              "proper_torsions": len(topology["Dihedrals"]), "periodic_impropers": len(impropers),
              "independent_chemical_roles": dict(sorted(Counter(roles.values()).items())),
              "nonperiodic_hamiltonian": "all-to-all geometric LJ + direct Coulomb (LAMMPS real constant332.06371), OPLS0/0/0.5; no tails/shifts",
              "nonperiodic_bounds": "expanded to contain all unwrapped positions; packed coordinates retained, controlled perturbations recorded separately",
              "packed_reference_kcal_mol": packed_reference, "packed_lammps_direct_kcal_mol": packed_measured,
              "packed_max_force_difference_kcal_mol_A": packed_force_discrepancy,
              "packed_force_limit": "LAMMPS dihedral_opls.cpp near-planar sin(phi) denominator guard; packed-state forces are recorded, not claimed exact",
              "controlled_geometry": controlled_metadata,
              "controlled_note": "fixed tiny coordinate perturbations explicitly avoid the third-party 1e-5 sine guard; generated case untouched",
              "reference_kcal_mol": reference, "lammps_direct_kcal_mol": measured,
              "canonical_RB_constant_removed_kcal_mol": offset,
              "max_force_difference_kcal_mol_A": max(abs(a - b) for x, y in zip(lammps_forces, reference_forces) for a, b in zip(x, y)),
              "finite_difference_components": 12, "finite_difference_max_difference_kcal_mol_A": max(differences),
              "periodic_PPPM_readback_kcal_mol": periodic_energies,
              "periodic_note": "separate generated PPPM run0 readback; NOT compared against the nonperiodic OpenMM reference",
              "worker_validation": manifest["validation"], "source_manifest_sha256": hashlib.sha256((case / "pet-model.json").read_bytes()).hexdigest()}
    (tmp_path / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
