"""Optional real-engine proof of the writer's ordered periodic impropers.

Run with the molecular-modeling Python, repository on PYTHONPATH and
STK_LAMMPS set to a real LAMMPS executable. This isolated four-atom fixture
compares twelve force components, including an independent finite difference;
it does not validate a PET material or parameterization.
"""
import json
import math
import os
import subprocess

import pytest

from suan.lammps.data import write_data


def _sub(a, b):
    return [x - y for x, y in zip(a, b)]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def _energy(positions, amplitude):
    a = _sub(positions[0], positions[1])
    b = _sub(positions[2], positions[1])
    c = _sub(positions[3], positions[2])
    n1 = _cross(a, b)
    n2 = _cross([-v for v in b], c)
    cosine = _dot(n1, n2) / math.sqrt(_dot(n1, n1) * _dot(n2, n2))
    return 2 * amplitude * (1 - cosine * cosine)


@pytest.mark.parametrize("amplitude", [1.1, 10.5], ids=["aromatic", "carbonyl"])
def test_ordered_improper_energy_and_forces(amplitude, tmp_path):
    program = os.environ.get("STK_LAMMPS")
    assert program, "set STK_LAMMPS to a real LAMMPS executable"
    import parmed as pmd
    import openmm as mm
    from openmm import unit

    positions = [[2.0, 3.0, 2.0], [2.0, 2.0, 2.0],
                 [3.0, 2.0, 2.0], [3.0, 3.0, 2.3]]
    structure = pmd.Structure()
    structure.combining_rule = "geometric"
    for index, position in enumerate(positions):
        atom = pmd.Atom(name=f"C{index}", atomic_number=6, mass=12.012, charge=0)
        atom.atom_type = pmd.AtomType("C", 1, 12.012, 6)
        atom.atom_type.set_lj_params(0, 1.5)
        atom.xx, atom.xy, atom.xz = position
        structure.add_atom(atom, "TEST", 1)
    parameter = pmd.DihedralType(amplitude, 2, 180)
    structure.dihedrals.append(pmd.Dihedral(*structure.atoms, improper=True, type=parameter))
    structure.box = [20, 20, 20, 90, 90, 90]
    data_path = tmp_path / "check.data"
    write_data(structure, data_path)
    assert "Impropers\n\n1 1 1 2 3 4\n" in data_path.read_text()
    (tmp_path / "check.in").write_text(
        "units real\natom_style full\nboundary p p p\npair_style lj/cut 3.0\n"
        "improper_style cvff\nread_data check.data\n"
        "thermo_style custom step pe eimp\nthermo_modify format float %.16g\n"
        "run 0\nwrite_dump all custom forces.dat id fx fy fz "
        "modify sort id format float %.16g\n", encoding="utf-8")
    result = subprocess.run([program, "-in", "check.in", "-log", "log.lammps", "-nocite"],
                            cwd=tmp_path, capture_output=True, text=True, timeout=60)
    (tmp_path / "screen.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Total wall time:" in result.stdout and "ERROR" not in result.stdout
    row = next(line.split() for line in result.stdout.splitlines()
               if len(line.split()) == 3 and line.split()[0] == "0")
    lammps_energy = float(row[2])
    assert float(row[1]) == pytest.approx(lammps_energy, abs=1e-12)
    force_text = (tmp_path / "forces.dat").read_text().splitlines()
    start = next(i for i, line in enumerate(force_text) if line.startswith("ITEM: ATOMS")) + 1
    lammps_forces = [list(map(float, line.split()[1:])) for line in force_text[start:start + 4]]

    system = mm.System()
    for _ in positions:
        system.addParticle(12.012)
    torsion = mm.PeriodicTorsionForce()
    torsion.addTorsion(0, 1, 2, 3, 2, math.pi, amplitude * 4.184)
    system.addForce(torsion)
    integrator = mm.VerletIntegrator(0.001)
    context = mm.Context(system, integrator, mm.Platform.getPlatformByName("Reference"))
    context.setPositions([[v * 0.1 for v in point] for point in positions])
    state = context.getState(getEnergy=True, getForces=True)
    openmm_energy = state.getPotentialEnergy().value_in_unit(unit.kilocalorie_per_mole)
    openmm_forces = [[float(v) for v in point] for point in
                     state.getForces(asNumpy=True).value_in_unit(unit.kilocalorie_per_mole / unit.angstrom)]
    assert lammps_energy == pytest.approx(_energy(positions, amplitude), abs=1e-10)
    assert lammps_energy == pytest.approx(openmm_energy, abs=1e-10)
    finite_forces = []
    step = 1e-5
    for index in range(4):
        components = []
        for axis in range(3):
            high = [point[:] for point in positions]
            low = [point[:] for point in positions]
            high[index][axis] += step
            low[index][axis] -= step
            force = -(_energy(high, amplitude) - _energy(low, amplitude)) / (2 * step)
            components.append(force)
            assert lammps_forces[index][axis] == pytest.approx(openmm_forces[index][axis], abs=1e-10)
            assert lammps_forces[index][axis] == pytest.approx(force, abs=1e-7)
        finite_forces.append(components)
    permuted = [positions[i] for i in (1, 0, 2, 3)]
    assert abs(_energy(permuted, amplitude) - lammps_energy) > 0.1
    report = {
        "scope": "isolated ordered improper energy/force equivalence, not PET property validation",
        "positions_A": positions, "cvff_coefficients": [amplitude, -1, 2],
        "atom_tuple": [1, 2, 3, 4], "analytic_energy_kcal_mol": _energy(positions, amplitude),
        "openmm_energy_kcal_mol": openmm_energy, "lammps_energy_kcal_mol": lammps_energy,
        "openmm_forces_kcal_mol_A": openmm_forces, "lammps_forces_kcal_mol_A": lammps_forces,
        "finite_difference_forces_kcal_mol_A": finite_forces,
        "central_first_permuted_energy_kcal_mol": _energy(permuted, amplitude),
    }
    (tmp_path / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
