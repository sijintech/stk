"""Write foyer/ParmEd OPLS structures as LAMMPS ``full`` data in ``real`` units.

No force-field assignment or charge correction happens here. Supported potentials
are Lennard-Jones, harmonic bonds/angles and RB torsions representable by OPLS.
Coordinates/box lengths are Angstrom, energies kcal/mol, angles degrees, charges e.
See https://docs.lammps.org/dihedral_opls.html and Howto_triclinic.html.
"""
import math
import os
from pathlib import Path
import tempfile


class DataError(ValueError):
    """The structure cannot be represented by this writer without losing physics."""


# foyer OPLS-AA contains RB coefficients rounded in kJ/mol to 1e-5.
RB_OFFSET_TOLERANCE = 5e-6  # kcal/mol, per torsion; reported in the data header


def _finite(value, name, *, minimum=None, positive=False):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise DataError(f"{name} must be a finite number") from None
    if not math.isfinite(number) or (minimum is not None and number < minimum) or (positive and number <= 0):
        raise DataError(f"Invalid {name}: expected a finite number in range")
    return number


def rb_to_opls(torsion_type):
    """RB uses cos(phi-pi); LAMMPS includes 1/2 in its OPLS energy expression.

    Reject a cos^5 term or constant above the source-coefficient rounding
    tolerance. The accumulated discarded rounding offset is recorded in data.
"""
    c = [_finite(getattr(torsion_type, f"c{i}"), f"RB c{i}") for i in range(6)]
    scale = max(1.0, *(abs(value) for value in c))
    if abs(c[5]) > 1e-10 * scale or abs(math.fsum(c[:5])) > RB_OFFSET_TOLERANCE:
        raise DataError("RB torsion is not exactly representable by OPLS (c5 or constant offset)")
    return tuple(_finite(v, "OPLS coefficient") for v in
                 (-2 * c[1] - 1.5 * c[3], -c[2] - c[4], -0.5 * c[3], -0.25 * c[4]))


def _cell(box):
    if box is None or len(box) != 6:
        raise DataError("A periodic box [a, b, c, alpha, beta, gamma] is required")
    a, b, c = [_finite(v, "box length", positive=True) for v in box[:3]]
    angles = [_finite(v, "box angle", positive=True) for v in box[3:]]
    if any(v >= 180 for v in angles):
        raise DataError("Box angles must be between 0 and 180 degrees")
    alpha, beta, gamma = map(math.radians, angles)
    xy, xz = b * math.cos(gamma), c * math.cos(beta)
    ly = b * math.sin(gamma)
    if ly <= 1e-12 * b:
        raise DataError("Box angles do not define a nondegenerate periodic cell")
    yz = (b * c * math.cos(alpha) - xy * xz) / ly
    z2 = c * c - xz * xz - yz * yz
    if not all(math.isfinite(v) for v in (xy, xz, ly, yz, z2)) or z2 <= 0 or ly <= 1e-12 * b:
        raise DataError("Box angles do not define a nondegenerate periodic cell")
    tilt = tuple(0.0 if abs(v) < 1e-12 else v for v in (xy, xz, yz))
    return (a, ly, math.sqrt(z2)), tilt


def _fmt(value):
    return format(value, ".16g")


def render_data(structure, *, allow_untyped_impropers=False):
    """Return deterministic text; validate the entire structure before writing.

Types share an ID only when their numeric parameters agree exactly. Molecule
IDs identify connected components of the bond graph (not ParmEd residues).
Unwrapped coordinates are preserved, with origin (0, 0, 0) and no image flags.
Velocities are deliberately not exported; initialize them in the input script.
"""
    atoms = list(structure.atoms)
    if not atoms:
        raise DataError("At least one typed atom is required")
    lengths, tilt = _cell(structure.box)
    for name in ("dihedrals", "urey_bradleys", "cmaps", "trigonal_angles", "out_of_plane_bends",
                 "pi_torsions", "stretch_bends", "torsion_torsions"):
        if getattr(structure, name, ()):
            raise DataError(f"Unsupported potential terms: {name}")
    impropers = list(getattr(structure, "impropers", ()))
    if impropers and (not allow_untyped_impropers or any(term.type is not None for term in impropers)):
        raise DataError("Improper terms are unsupported; only untyped impropers may be explicitly ignored")
    if getattr(structure, "combining_rule", "geometric") != "geometric":
        raise DataError("OPLS writer requires geometric Lennard-Jones mixing")

    atom_ids = {id(atom): i + 1 for i, atom in enumerate(atoms)}
    if len(atom_ids) != len(atoms):
        raise DataError("Duplicate atom object")
    parent = list(range(len(atoms)))
    neighbours = [set() for _ in atoms]

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def members(term, count):
        try:
            ids = tuple(atom_ids[id(getattr(term, f"atom{i}"))] for i in range(1, count + 1))
        except (KeyError, AttributeError):
            raise DataError("Topology term references an atom outside the structure") from None
        if len(set(ids)) != count:
            raise DataError("Topology term repeats an atom")
        return ids

    def intern(table, key):
        if key not in table:
            table[key] = len(table) + 1
        return table[key]

    types, atom_rows = {}, []
    for atom in atoms:
        try:
            atom_type = atom.atom_type
            if getattr(atom_type, "nbfix", {}) or getattr(atom, "exclusion_partners", ()):
                raise DataError("Custom nonbonded pairs/exclusions are unsupported")
            key = (_finite(atom.mass, "mass", positive=True),
                   _finite(atom.epsilon, "epsilon", minimum=0), _finite(atom.sigma, "sigma", minimum=0))
            # A distinct 1-4 LJ potential needs PairIJ/special-pair support.
            if atom_type.epsilon_14 != atom_type.epsilon or atom_type.rmin_14 != atom_type.rmin:
                raise DataError("Distinct 1-4 Lennard-Jones parameters are unsupported")
            charge = _finite(atom.charge, "charge")
            xyz = tuple(_finite(getattr(atom, axis), axis) for axis in ("xx", "xy", "xz"))
        except AttributeError:
            raise DataError("Atoms must have assigned ParmEd masses, LJ parameters, charges and coordinates") from None
        atom_rows.append((intern(types, key), charge, *xyz))

    sections = {}
    for name, section, count in (("bonds", "Bond", 2), ("angles", "Angle", 3), ("rb_torsions", "Dihedral", 4)):
        table, rows = {}, []
        for term in getattr(structure, name, ()):
            ids = members(term, count)
            if term.type is None:
                raise DataError(f"Missing {section.lower()} parameters")
            if name == "bonds":
                key = (_finite(term.type.k, "bond k", minimum=0), _finite(term.type.req, "bond length", positive=True))
                parent[root(ids[1] - 1)] = root(ids[0] - 1)
                neighbours[ids[0] - 1].add(ids[1] - 1)
                neighbours[ids[1] - 1].add(ids[0] - 1)
            elif name == "angles":
                key = (_finite(term.type.k, "angle k", minimum=0), _finite(term.type.theteq, "angle", minimum=0))
                if key[1] > 180:
                    raise DataError("Equilibrium angle exceeds 180 degrees")
            else:
                if getattr(term, "improper", False):
                    raise DataError("RB improper torsions are unsupported")
                key = rb_to_opls(term.type)
                if getattr(term.type, "scee", 1.0) != 1.0 or getattr(term.type, "scnb", 1.0) != 1.0:
                    raise DataError("RB per-torsion 1-4 scaling is unsupported; set OPLS special_bonds in the script")
            rows.append((intern(table, key), *ids))
        sections[section] = (table, rows)
    # foyer materializes OpenMM's special pairs as ParmEd adjustments. Only
    # the standard OPLS 1-2/1-3 exclusions and half-strength 1-4 pairs fit here.
    for pair in getattr(structure, "adjusts", ()):
        i, j = (v - 1 for v in members(pair, 2))
        seen, frontier, distance = {i}, {i}, None
        for depth in range(1, 4):
            frontier = set().union(*(neighbours[k] for k in frontier)) - seen
            if j in frontier:
                distance = depth
                break
            seen.update(frontier)
        if distance is None or pair.type is None:
            raise DataError("Nonbonded adjustment is not a standard OPLS special pair")
        scale = 0.5 if distance == 3 else 0.0
        expected_epsilon = math.sqrt(atoms[i].epsilon * atoms[j].epsilon) * scale
        expected_rmin = math.sqrt(atoms[i].rmin * atoms[j].rmin) * 2
        if not (math.isclose(_finite(pair.type.chgscale, "special Coulomb scale"), scale, abs_tol=1e-12)
                and math.isclose(_finite(pair.type.epsilon, "special epsilon"), expected_epsilon, abs_tol=1e-10)
                and (scale == 0 or math.isclose(_finite(pair.type.rmin, "special rmin"), expected_rmin, abs_tol=1e-8))):
            raise DataError("Nonbonded adjustment differs from OPLS special_bonds lj/coul 0 0 0.5")
    molecules = {}
    molecule_ids = [intern(molecules, root(i)) for i in range(len(atoms))]

    lines = ["STK LAMMPS data; atom_style full; units real; charges preserved", "",
             f"{len(atoms)} atoms"]
    for section, (_, rows) in sections.items():
        lines.append(f"{len(rows)} {section.lower()}s")
    lines.extend(["0 impropers", "", f"{len(types)} atom types"])
    for section, (table, _) in sections.items():
        lines.append(f"{len(table)} {section.lower()} types")
    lines.extend(["0 improper types", ""])
    for axis, length in zip("xyz", lengths):
        lines.append(f"0 {_fmt(length)} {axis}lo {axis}hi")
    # Include even zero tilt for consistent GMSO/LAMMPS triclinic handling.
    lines.append(" ".join(map(_fmt, tilt)) + " xy xz yz")
    lines.extend(["", "# pair_modify mix geometric; special_bonds lj/coul 0 0 0.5",
                  f"# explicitly ignored untyped impropers: {len(impropers)}",
                  "# RB rounding constant omitted (kcal/mol): " + _fmt(math.fsum(
                      getattr(term.type, f"c{i}") for term in getattr(structure, "rb_torsions", ()) for i in range(5))),
                  "", "Masses", ""])
    lines.extend(f"{index} {_fmt(key[0])}" for key, index in types.items())
    lines.extend(["", "Pair Coeffs", ""])
    lines.extend(f"{index} {_fmt(key[1])} {_fmt(key[2])}" for key, index in types.items())
    for section, (table, _) in sections.items():
        if table:
            lines.extend(["", f"{section} Coeffs", ""])
            lines.extend(f"{index} " + " ".join(map(_fmt, key)) for key, index in table.items())
    lines.extend(["", "Atoms # full", ""])
    lines.extend(f"{i} {molecule} {row[0]} " + " ".join(map(_fmt, row[1:]))
                 for i, (molecule, row) in enumerate(zip(molecule_ids, atom_rows), 1))
    for section, (_, rows) in sections.items():
        if rows:
            lines.extend(["", f"{section}s", ""])
            lines.extend(f"{i} " + " ".join(map(str, row)) for i, row in enumerate(rows, 1))
    return "\n".join(lines) + "\n"


def write_data(structure, path, *, allow_untyped_impropers=False):
    """Validate then atomically replace ``path``; failure preserves an existing file."""
    data = render_data(structure, allow_untyped_impropers=allow_untyped_impropers)
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
