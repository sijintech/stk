"""Dry, neutral COOH/OH PET: an explicit literature OPLS-AA/MK adaptation.

Core metadata/validation are standard-library only. Molecular packages are
imported only by the optional module's isolated worker, never for a refresh.
"""
from collections import Counter
from importlib.resources import files
import json
import math

PROFILE = "pet-opls-mk2022-v1.json"
FORCEFIELD = "pet-opls-mk2022-v1.xml"
PROFILE_ID = "stk.pet.opls-mk2022/1"
MAX_ATOMS = 50000
MAX_CHAIN_LENGTH = 20  # Bound whole-chain distance-geometry memory/preprocessing.
DEFAULT_PARAMETERS = {"chain_length": 4, "chain_count": 6, "packing_density": 250.0, "seed": 4928459}
OUTPUTS = ("pet.data", "model.in", "forcefield.xml", "pet-model.json", "in.pet", "in.tg", "in.modulus", "in.diffusion")


def validate_parameters(parameters):
    """Initial packing density in kg/m3; it is not an equilibrium prediction."""
    if not isinstance(parameters, dict) or set(parameters) - set(DEFAULT_PARAMETERS):
        raise ValueError("PET parameters must be chain_length, chain_count, packing_density and seed")
    values = {**DEFAULT_PARAMETERS, **parameters}
    for key, lower, upper in (("chain_length", 2, MAX_CHAIN_LENGTH), ("chain_count", 1, 1000), ("seed", 1, 2147483647)):
        if type(values[key]) is not int or not lower <= values[key] <= upper:
            raise ValueError(f"{key} must be an integer in [{lower}, {upper}]")
    density = values["packing_density"]
    if type(density) not in (int, float) or not math.isfinite(density) or not 1 <= density <= 2000:
        raise ValueError("packing_density must be finite in [1, 2000] kg/m3")
    values["packing_density"] = float(density)
    if (22 * values["chain_length"] + 3) * values["chain_count"] > MAX_ATOMS:
        raise ValueError(f"PET modeling is limited to {MAX_ATOMS} atoms")
    return values


def profile():
    return json.loads(files("suan.lammps").joinpath("forcefields", PROFILE).read_text(encoding="utf-8"))


def forcefield_text():
    return files("suan.lammps").joinpath("forcefields", FORCEFIELD).read_text(encoding="utf-8")


def expected_types(length):
    return {"PET_CA": 6*length, "PET_HA": 4*length, "PET_CO_ESTER": 2*length-1,
            "PET_O_ESTER": 2*length-1, "PET_OES": 2*length-1, "PET_CT_ESTER": 2*length-1,
            "PET_HAE": 4*length-2, "PET_CO_ACID": 1, "PET_O_ACID": 1,
            "PET_OH_ACID": 1, "PET_HO_ACID": 1, "PET_CT_OH": 1, "PET_HC_OH": 2,
            "PET_OH_TAIL": 1, "PET_HO_TAIL": 1}


def validate_structure(structure, parameters):
    """Verify formula, local typing, charges and connected chains independently."""
    values = validate_parameters(parameters)
    n, count = values["chain_length"], values["chain_count"]
    atoms = list(structure.atoms)
    if len(atoms) != (22*n+3)*count:
        raise ValueError("PET atom count does not match COOH/OH terminal chemistry")
    atomic = Counter(a.atomic_number for a in atoms)
    if atomic != {6: 10*n*count, 1: (8*n+2)*count, 8: (4*n+1)*count}:
        raise ValueError("PET composition must be C(10N) H(8N+2) O(4N+1) per chain")
    index = {id(atom): i for i, atom in enumerate(atoms)}
    neighbors = [set() for _ in atoms]
    for bond in structure.bonds:
        i, j = index[id(bond.atom1)], index[id(bond.atom2)]
        neighbors[i].add(j)
        neighbors[j].add(i)
    groups, remaining = [], set(range(len(atoms)))
    while remaining:
        group, frontier = set(), {min(remaining)}
        while frontier:
            group.update(frontier)
            frontier = set().union(*(neighbors[i] for i in frontier)) - group
        remaining.difference_update(group)
        groups.append(sorted(group))
    if len(groups) != count:
        raise ValueError("PET connected chain count is incorrect")
    if (len(structure.bonds), len(structure.angles), len(structure.rb_torsions), len(structure.dihedrals)) != (
            (23*n+2)*count, (38*n+1)*count, 51*n*count, 8*n*count):
        raise ValueError("PET bond/angle/proper/planar-improper topology is incomplete")
    if structure.impropers:
        raise ValueError("PET has unexpected additional harmonic/untyped improper terms")
    parameters_by_type = {item["name"]: item for item in profile()["atom_types"]}
    charges = []
    for group in groups:
        if Counter(atoms[i].type for i in group) != expected_types(n):
            raise ValueError("PET chain typing does not match the complete published charge scheme")
        total = math.fsum(atoms[i].charge for i in group)
        if not math.isfinite(total) or abs(total) > 1e-10:
            raise ValueError("Each PET chain must be neutral; do not subtract a mean charge")
        charges.append(total)
    for atom in atoms:
        expected = parameters_by_type[atom.type]
        degree = 1 if expected["element"] == "H" or atom.type in ("PET_O_ACID", "PET_O_ESTER") else (
            4 if atom.type in ("PET_CT_ESTER", "PET_CT_OH") else
            3 if atom.type in ("PET_CA", "PET_CO_ACID", "PET_CO_ESTER") else 2)
        if len(neighbors[index[id(atom)]]) != degree:
            raise ValueError("PET local valence differs from the specified terminal chemistry")
        sigma, epsilon, mass = expected["lj_sigma_A_epsilon_kcal_mass"]
        if not all(math.isclose(actual, target, rel_tol=1e-10, abs_tol=1e-10) for actual, target in
                   ((atom.charge, expected["charge_e"]), (atom.mass, mass), (atom.sigma, sigma), (atom.epsilon, epsilon))):
            raise ValueError("PET charge/LJ/mass differs from the versioned literature profile")
    if any(not term.improper or term.type is None or term.type.per != 2 or term.type.phase != 180
           for term in structure.dihedrals):
        raise ValueError("PET requires explicit periodic planar impropers")
    return {"formula_per_chain": {"C": 10*n, "H": 8*n+2, "O": 4*n+1},
            "chain_count": len(groups), "chain_charge_e": charges,
            "atom_types": dict(sorted(Counter(a.type for a in atoms).items())),
            "atoms": len(atoms), "bonds": len(structure.bonds), "angles": len(structure.angles),
            "proper_torsions": len(structure.rb_torsions),
            "periodic_impropers": len(structure.dihedrals)}
