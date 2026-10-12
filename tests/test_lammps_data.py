"""Physical and failure boundaries without optional molecular-modeling packages."""
import hashlib
import math
from types import SimpleNamespace as NS

import pytest

from suan.lammps.data import DataError, periodic_improper_to_cvff, rb_to_opls, render_data, write_data


def structure():
    # Different names and object identities, equal physical LJ parameters.
    atoms = [NS(atom_type=NS(epsilon=0.2, epsilon_14=0.2, rmin=1.5, rmin_14=1.5, nbfix={}),
                mass=12.0, epsilon=0.2, sigma=3.0, rmin=1.5, charge=q,
                xx=1.0 + i, xy=2.0, xz=3.0, exclusion_partners=[]) for i, q in enumerate([0.13, -0.2, 0.0, 0.4])]

    def term(indices, kind):
        return NS(**{f"atom{i}": atoms[index] for i, index in enumerate(indices, 1)}, type=kind)

    bonds = [term([i, i + 1], NS(k=200.0, req=1.4)) for i in range(3)]
    angles = [term([0, 1, 2], NS(k=40.0, theteq=110.0))]
    torsions = [term([0, 1, 2, 3], NS(c0=1.0, c1=-1.0, c2=0.0, c3=0.0, c4=0.0, c5=0.0, scee=1.0, scnb=1.0))]
    return NS(atoms=atoms, bonds=bonds, angles=angles, rb_torsions=torsions, impropers=[],
              box=[10.0, 11.0, 12.0, 90.0, 90.0, 90.0], combining_rule="geometric", adjusts=[])


def test_charges_types_topology_and_no_input_mutation(tmp_path):
    s = structure()
    s.atoms.append(NS(**vars(s.atoms[0])))  # disconnected atom, even if it shared a ParmEd residue
    data = render_data(s)
    assert "1 atom types" in data and "1 bond types" in data
    assert "1 1 1 0.13 1 2 3" in data and "2 1 1 -0.2 2 2 3" in data
    assert "5 2 1 0.13 1 2 3" in data
    assert "Bond Coeffs\n\n1 200 1.4" in data  # LAMMPS K already includes harmonic 1/2
    assert "Angle Coeffs\n\n1 40 110" in data
    assert "Dihedral Coeffs\n\n1 2" in data
    assert [a.charge for a in s.atoms] == [0.13, -0.2, 0.0, 0.4, 0.13]
    assert data == render_data(s)
    path = tmp_path / "system.data"
    write_data(s, path)
    assert path.read_text() == data
    s.atoms[0].charge = float("nan")
    with pytest.raises(DataError):
        write_data(s, path)
    assert path.read_text() == data and list(tmp_path.iterdir()) == [path]


def test_rb_opls_energy_equivalence_over_whole_period():
    t = NS(c0=2.0, c1=-1.0, c2=0.0, c3=-2.0, c4=1.0, c5=0.0)
    k = rb_to_opls(t)
    for degree in range(-180, 181, 7):
        phi = math.radians(degree)
        rb = sum(getattr(t, f"c{i}") * math.cos(phi - math.pi) ** i for i in range(6))
        opls = sum(v * (1 + (-1) ** (i + 1) * math.cos(i * phi)) / 2 for i, v in enumerate(k, 1))
        assert rb == pytest.approx(opls, abs=1e-12)
    for field in ("c0", "c5"):
        invalid = NS(**vars(t))
        setattr(invalid, field, getattr(t, field) + 0.1)
        with pytest.raises(DataError, match="representable"):
            rb_to_opls(invalid)


def test_triclinic_preserves_volume_and_cell_vectors():
    s = structure()
    s.box = [10, 11, 12, 80, 75, 70]
    data = render_data(s)
    ly = float(next(line for line in data.splitlines() if "ylo" in line).split()[1])
    lz = float(next(line for line in data.splitlines() if "zlo" in line).split()[1])
    xy, xz, yz = map(float, next(line for line in data.splitlines() if "xy xz yz" in line).split()[:3])
    assert math.hypot(xy, ly) == pytest.approx(11)
    assert math.sqrt(xz*xz + yz*yz + lz*lz) == pytest.approx(12)
    assert (xy*xz + ly*yz) / (11*12) == pytest.approx(math.cos(math.radians(80)))
    assert xy/11 == pytest.approx(math.cos(math.radians(70)))
    assert xz/12 == pytest.approx(math.cos(math.radians(75)))


@pytest.mark.parametrize("change", [
    lambda s: setattr(s, "box", None),
    lambda s: setattr(s, "box", [1, 1, 1, 1, 1, 179]),
    lambda s: setattr(s, "dihedrals", [object()]),
    lambda s: setattr(s, "urey_bradleys", [object()]),
    lambda s: setattr(s, "combining_rule", "lorentz"),
    lambda s: setattr(s.atoms[0].atom_type, "epsilon_14", 0.1),
    lambda s: setattr(s.atoms[0].atom_type, "nbfix", {"other": 1}),
    lambda s: setattr(s.atoms[0], "exclusion_partners", [s.atoms[-1]]),
    lambda s: setattr(s.bonds[0], "type", None),
    lambda s: setattr(s.bonds[0], "atom2", object()),
    lambda s: setattr(s.bonds[0], "atom2", s.bonds[0].atom1),
    lambda s: setattr(s.atoms[0], "mass", -1),
    lambda s: setattr(s.atoms[0], "xz", float("inf")),
    lambda s: setattr(s.rb_torsions[0].type, "scnb", 2),
])
def test_rejects_lossy_or_invalid_structure(change):
    s = structure()
    change(s)
    with pytest.raises(DataError):
        render_data(s)


def test_impropers_require_explicit_opt_in_and_typed_impropers_always_fail():
    s = structure()
    s.impropers = [NS(type=None)]
    with pytest.raises(DataError, match="Improper"):
        render_data(s)
    assert "explicitly ignored untyped impropers: 1" in render_data(s, allow_untyped_impropers=True)
    s.impropers[0].type = object()
    with pytest.raises(DataError):
        render_data(s, allow_untyped_impropers=True)


def test_opls_special_pairs_are_checked():
    s = structure()
    s.adjusts = [NS(atom1=s.atoms[0], atom2=s.atoms[3], type=NS(rmin=3.0, epsilon=0.1, chgscale=0.5))]
    render_data(s)
    s.adjusts[0].type.chgscale = 1.0
    with pytest.raises(DataError, match="special_bonds"):
        render_data(s)


def periodic_improper(s, order=(0, 1, 2, 3), amplitude=10.5):
    return NS(**{f"atom{i}": s.atoms[index] for i, index in enumerate(order, 1)},
              improper=True, type=NS(phi_k=amplitude, per=2, phase=180))


def test_no_periodic_impropers_preserves_pre_extension_data_bytes():
    # Recorded from the released writer and this existing topology fixture.
    assert hashlib.sha256(render_data(structure()).encode()).hexdigest() == (
        "32c23eb08007dd581d66507fd1c2e1964a2b7b2b7689cd3179236571881ca977")


def test_periodic_improper_cvff_energy_and_derivative_over_whole_period():
    for amplitude in (0.0, 1.1, 10.5):
        source = NS(phi_k=amplitude, per=2, phase=180)
        k, sign, period = periodic_improper_to_cvff(source)
        for degree in range(-180, 181, 7):
            phi = math.radians(degree)
            expected = amplitude * (1 + math.cos(2 * phi - math.pi))
            cvff = k * (1 + sign * math.cos(period * phi))
            assert cvff == pytest.approx(expected, abs=1e-12)
            step = 1e-5
            derivative = (k * (1 + sign * math.cos(period * (phi + step))) -
                          k * (1 + sign * math.cos(period * (phi - step)))) / (2 * step)
            assert derivative == pytest.approx(-2 * amplitude * math.sin(2 * phi - math.pi), abs=5e-9)


def test_periodic_improper_types_members_order_and_atomic_failure(tmp_path):
    s = structure()
    original = periodic_improper(s, order=(3, 1, 0, 2))
    s.dihedrals = [original, periodic_improper(s), periodic_improper(s, amplitude=1.1)]
    data = render_data(s)
    assert "3 impropers\n" in data and "2 improper types\n" in data
    assert "0 impropers\n" not in data
    assert "Improper Coeffs\n\n1 10.5 -1 2\n2 1.1 -1 2" in data
    assert "Impropers\n\n1 1 4 2 1 3\n2 1 1 2 3 4\n3 2 1 2 3 4" in data
    assert "# improper_style cvff; original atom order preserved" in data
    assert original.atom1 is s.atoms[3] and original.atom3 is s.atoms[0]
    path = tmp_path / "system.data"
    write_data(s, path)
    original.type.phase = 90
    with pytest.raises(DataError, match="phase 180"):
        write_data(s, path)
    assert path.read_text() == data and list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("change", [
    lambda t: setattr(t, "improper", False),
    lambda t: setattr(t, "type", None),
    lambda t: setattr(t, "type", [t.type]),
    lambda t: setattr(t.type, "phi_k", -1),
    lambda t: setattr(t.type, "phi_k", float("inf")),
    lambda t: setattr(t.type, "phi_k", float("nan")),
    lambda t: setattr(t.type, "per", 3),
    lambda t: setattr(t.type, "per", 2.01),
    lambda t: setattr(t.type, "per", float("nan")),
    lambda t: setattr(t.type, "phase", 0),
    lambda t: setattr(t.type, "phase", 90),
    lambda t: setattr(t.type, "phase", float("nan")),
    lambda t: setattr(t, "atom2", object()),
    lambda t: setattr(t, "atom4", t.atom1),
])
def test_periodic_improper_rejects_lossy_conversion(change):
    s = structure()
    s.dihedrals = [periodic_improper(s)]
    change(s.dihedrals[0])
    with pytest.raises(DataError):
        render_data(s, allow_untyped_impropers=True)


def test_periodic_improper_does_not_enable_ignoring_untyped_impropers():
    s = structure()
    s.dihedrals = [periodic_improper(s)]
    s.impropers = [NS(type=None)]
    with pytest.raises(DataError, match="Improper"):
        render_data(s)
    data = render_data(s, allow_untyped_impropers=True)
    assert "1 impropers\n" in data and "explicitly ignored untyped impropers: 1" in data
    s.impropers[0].type = NS(psi_k=10, psi_eq=0)
    with pytest.raises(DataError):
        render_data(s, allow_untyped_impropers=True)
