"""Physical and failure boundaries without optional molecular-modeling packages."""
import math
from types import SimpleNamespace as NS

import pytest

from suan.lammps.data import DataError, rb_to_opls, render_data, write_data


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
