"""Offline PET builder, executed only inside the detected molecular module.

The desktop launcher supplies an isolated interpreter, a whitelist environment,
an explicit Packmol binary and a fresh staging directory. Importing core STK
does not import mBuild, Foyer, RDKit or ParmEd.
"""
import argparse
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from .data import write_data
from .pet import (PROFILE_ID, forcefield_text, profile,
                  validate_parameters, validate_structure)
from .templates import template_text

AVOGADRO_MASS_KG = 1.66053906660e-27


def chain_smiles(length):
    """One acid end and one alcohol end; N terephthalate/ethylene units."""
    return "O=C(O)c1ccc(cc1)C(=O)OCCO" + "C(=O)c1ccc(cc1)C(=O)OCCO" * (length - 1)


def _chain(length, seed):
    """Seeded ETKDG with explicit fallback; retain its actual coordinates."""
    from rdkit import Chem
    from rdkit.Chem import AllChem
    import mbuild as mb
    import numpy as np
    molecule = Chem.AddHs(Chem.MolFromSmiles(chain_smiles(length)))
    attempts = []
    for random_coordinates in (False, True):
        parameters = AllChem.ETKDGv3()
        if not hasattr(parameters, "timeout"):
            raise ValueError("PET modeling requires RDKit with embedding timeout support; update the molecular module")
        parameters.randomSeed, parameters.numThreads = seed, 1
        parameters.useRandomCoords = random_coordinates
        parameters.maxIterations, parameters.timeout = 30, 45
        parameters.trackFailures = True
        start = time.monotonic()
        conformer = AllChem.EmbedMolecule(molecule, parameters)
        attempts.append({"use_random_coordinates": random_coordinates, "return_code": conformer,
                         "seconds": time.monotonic() - start,
                         "failure_counts": list(parameters.GetFailureCounts())})
        if conformer >= 0:
            break
    else:
        raise ValueError(f"RDKit could not construct PET DP{length} with seed {seed}; try another seed or shorter chains")
    uff_status = AllChem.UFFOptimizeMolecule(molecule, maxIters=200)
    positions = np.asarray(molecule.GetConformer(conformer).GetPositions())
    if uff_status not in (0, 1) or not np.isfinite(positions).all():
        raise ValueError("PET initial UFF relaxation did not produce finite coordinates")
    # mBuild.from_rdkit would embed again, discarding the chosen conformer.
    chain = mb.Compound(name="PET COOH/OH")
    particles = [mb.Particle(name=atom.GetSymbol(), element=atom.GetSymbol(), pos=positions[i] / 10)
                 for i, atom in enumerate(molecule.GetAtoms())]
    chain.add(particles)
    for bond in molecule.GetBonds():
        chain.add_bond((particles[bond.GetBeginAtomIdx()], particles[bond.GetEndAtomIdx()]),
                       bond_order=bond.GetBondTypeAsDouble())
    audit = {"method": "RDKit ETKDGv3; deterministic default then random-coordinate fallback",
             "seed": seed, "embedding_attempts": attempts, "max_attempts_per_mode": 30,
             "rdkit_internal_timeout_seconds": 45, "uff_max_iterations": 200, "uff_status": uff_status,
             "timeout_scope": "RDKit timeout does not cover all preprocessing; launcher provides the hard 1800 s wall budget",
             "coordinate_sha256": hashlib.sha256(positions.astype('<f8').tobytes()).hexdigest(),
             "coordinate_hash_units": "Angstrom, little-endian float64, RDKit atom order"}
    return chain, audit


def add_planar_impropers(structure):
    """Construct source-ordered tuples independently of Foyer permutations."""
    import parmed as pmd
    if structure.dihedrals or any(term.type is not None for term in structure.impropers):
        raise ValueError("Unexpected typed/periodic Foyer impropers; refusing to replace them")
    discarded = len(structure.impropers)
    structure.impropers.clear()
    definitions = profile()["impropers"]
    kinds = {key: pmd.DihedralType(definitions[key]["phi_k_kcal_mol"], 2, 180)
             for key in ("carbonyl", "aromatic")}
    structure.dihedral_types.extend(kinds.values())
    neighbors = {atom: [] for atom in structure.atoms}
    for bond in structure.bonds:
        neighbors[bond.atom1].append(bond.atom2)
        neighbors[bond.atom2].append(bond.atom1)
    for center, bonded in neighbors.items():
        if center.type in ("PET_CO_ACID", "PET_CO_ESTER"):
            carbonyl = [a for a in bonded if a.type in ("PET_O_ACID", "PET_O_ESTER")]
            aryl = [a for a in bonded if a.type == "PET_CA"]
            bridge = [a for a in bonded if a.type in ("PET_OH_ACID", "PET_OES")]
            if len(bonded) != 3 or tuple(map(len, (carbonyl, aryl, bridge))) != (1, 1, 1):
                raise ValueError("PET carbonyl connectivity is incorrect")
            ordered, kind = (carbonyl[0], center, aryl[0], bridge[0]), "carbonyl"
        elif center.type == "PET_CA":
            ring = sorted((a for a in bonded if a.type == "PET_CA"), key=lambda a: a.idx)
            external = [a for a in bonded if a.type in ("PET_HA", "PET_CO_ACID", "PET_CO_ESTER")]
            if len(bonded) != 3 or len(ring) != 2 or len(external) != 1:
                raise ValueError("PET aromatic connectivity is incorrect")
            ordered, kind = (external[0], center, *ring), "aromatic"
        else:
            continue
        structure.dihedrals.append(pmd.Dihedral(*ordered, improper=True, ignore_end=True, type=kinds[kind]))
    return {"untyped_foyer_candidates_removed": discarded,
            "explicit_periodic_planar_impropers": len(structure.dihedrals),
            "ordering": "central atom SECOND; explicit source tuples preserved"}


def _strict_packmol(input_text, filled_xyz, temp_file=None, packmol_file=None):
    """Reject mBuild's imperfect-packing fallback, retain no unbounded output."""
    import mbuild.packing as packing
    if packmol_file is not None:
        Path(packmol_file).write_text(input_text, encoding="utf-8")
    with tempfile.TemporaryFile(mode="w+") as source, tempfile.TemporaryFile(mode="w+b") as log:
        source.write(input_text)
        source.seek(0)
        process = subprocess.Popen([packing.PACKMOL], stdin=source, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 900
        try:
            while process.poll() is None:
                if os.fstat(log.fileno()).st_size > 8 * 1024 * 1024 or time.monotonic() > deadline:
                    raise ValueError("Packmol exceeded its output/time budget")
                time.sleep(0.02)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
        size = os.fstat(log.fileno()).st_size
        log.seek(0 if size <= 8 * 1024 * 1024 else max(0, size - 8192))
        output = log.read(8 * 1024 * 1024).decode("utf-8", errors="replace")
        if process.returncode or size > 8 * 1024 * 1024 or "ERROR" in output or "WITHOUT PERFECT PACKING" in output or "Success!" not in output:
            raise ValueError("Packmol did not produce a verified perfect packing: " + output[-2000:])
    if temp_file is not None:
        shutil.copyfile(filled_xyz.name, temp_file)
    version_line = re.search(r"\bVersion\s+([0-9][0-9A-Za-z._-]*)", output)
    return {"version": version_line.group(1) if version_line else None, "perfect_packing_verified": True}


def _packing_audit(box, prototype_xyz, side_nm):
    """Check interchain and self-image overlaps without an N squared matrix."""
    import numpy as np
    from scipy.spatial import cKDTree
    xyz = np.asarray(box.xyz)
    prototype_xyz = np.asarray(prototype_xyz)
    atoms_per_chain = len(prototype_xyz)
    wrapped = np.mod(xyz, side_nm)
    tree = cKDTree(wrapped, boxsize=side_nm)
    # Stream each neighborhood: even a broken all-coincident packing must not
    # allocate a quadratic query_pairs result before being rejected.
    for i, position in enumerate(wrapped):
        for j in tree.query_ball_point(position, 0.199):
            if j <= i:
                continue
            delta = xyz[j] - xyz[i]
            nearest = delta - side_nm * np.rint(delta / side_nm)
            # A wrapped covalent bond is legitimate. Compare same-chain pairs
            # with the rigid prototype to distinguish it from self overlap.
            original = float(np.linalg.norm(prototype_xyz[j % atoms_per_chain] - prototype_xyz[i % atoms_per_chain]))
            if i // atoms_per_chain != j // atoms_per_chain or original >= 0.199:
                distance = float(np.linalg.norm(nearest))
                raise ValueError(f"PET packing has a periodic interchain/self-image distance {distance * 10:.6g} A below 1.99 A")
    return {"periodic_interchain_self_image_overlap_threshold_A": 1.99,
            "periodic_interchain_self_image_overlap_count": 0}


def typed_structure(parameters, forcefield_path, *, packmol=None):
    """Build and type dry PET; forcefield_path is the shipped complete XML."""
    import foyer
    import mbuild as mb
    import mbuild.packing as packing
    import numpy as np
    values = validate_parameters(parameters)
    start = time.monotonic()
    polymer, geometry_audit = _chain(values["chain_length"], values["seed"])
    geometry_seconds = time.monotonic() - start
    n, count = values["chain_length"], values["chain_count"]
    # Published masses, rather than mBuild's slightly different element masses.
    masses = {a["name"]: a["lj_sigma_A_epsilon_kcal_mass"][2] for a in profile()["atom_types"]}
    from .pet import expected_types
    chain_mass = math.fsum(masses[name] * number for name, number in expected_types(n).items())
    side_nm = (chain_mass * count * AVOGADRO_MASS_KG / values["packing_density"]) ** (1 / 3) * 1e9
    # A rigid conformer is packed, not folded by Packmol. Fail honestly if it
    # cannot fit; long chains need suitable conformers and lower initial density.
    if float(np.max(np.ptp(polymer.xyz, axis=0))) > side_nm * math.sqrt(3):
        raise ValueError("PET conformer cannot fit this initial box; lower packing density or use shorter chains")
    start = time.monotonic()
    if packmol is not None:
        packing.PACKMOL = str(Path(packmol).resolve(strict=True))
    original_runner = packing._run_packmol
    packing_report = {}

    def run_packmol(*args, **kwargs):
        packing_report.update(_strict_packmol(*args, **kwargs))

    try:
        packing._run_packmol = run_packmol
        box = mb.fill_box(compound=polymer, n_compounds=count, box=mb.Box(lengths=[side_nm] * 3),
                          seed=values["seed"], edge=0, overlap=0.2, use_pbc=True)
    finally:
        packing._run_packmol = original_runner
    packing_audit = _packing_audit(box, polymer.xyz, side_nm)
    packing_seconds = time.monotonic() - start
    start = time.monotonic()
    ff = foyer.Forcefield(forcefield_files=[str(forcefield_path)])
    structure = ff.apply(box, assert_improper_params=False)
    # Foyer/ParmEd preserves input element masses despite XML mass declarations.
    # Adopt the published S2 masses explicitly and archive that conversion.
    original_masses = dict(sorted({atom.type: atom.mass for atom in structure.atoms}.items()))
    for atom in structure.atoms:
        atom.mass = masses[atom.type]
        atom.atom_type.mass = atom.mass
    improper_audit = add_planar_impropers(structure)
    validation = validate_structure(structure, values)
    if validation["periodic_impropers"] != 8 * n * count:
        raise ValueError("PET must have one explicit planar improper per sp2 center")
    validation.update(improper_audit)
    validation["initial_geometry"] = geometry_audit
    validation.update(packing_audit)
    validation["packmol"] = packing_report
    validation["input_element_masses_replaced_amu"] = original_masses
    validation.update({"box_lengths_A": list(map(float, structure.box[:3])),
                       "initial_density_kg_m3": chain_mass * count * AVOGADRO_MASS_KG /
                       math.prod(float(length) * 1e-10 for length in structure.box[:3])})
    return structure, validation, {"initial_geometry": geometry_seconds, "packmol": packing_seconds,
                                   "foyer_and_validation": time.monotonic() - start}


MODEL_IN = """# STK dry COOH/OH PET OPLS-AA/MK 2022 adaptation; see pet-model.json.
# Coulomb PPPM differs from the source paper's shifted 12 A cutoff.
pair_style lj/cut/coul/long 12.0
pair_modify mix geometric
bond_style harmonic
angle_style harmonic
dihedral_style opls
improper_style cvff
special_bonds lj/coul 0.0 0.0 0.5
read_data pet.data
kspace_style pppm 1.0e-4
neighbor 2.0 bin
neigh_modify every 1 delay 0 check yes
"""

PREPARATION_IN = """# Initial relaxation only: this is not a converged amorphous PET property calculation.
# Long/high-temperature annealing, densification, chain-size and seed studies are required.
units real
atom_style full
boundary p p p
variable temperature index 500
variable pressure index 1
variable steps index 10000
variable timestep index 1
variable seed index 4928459
variable equilibration_steps index 10000
variable sample_interval index 100
include model.in
thermo ${sample_interval}
thermo_style custom step temp press density pe ebond eangle edihed eimp evdwl ecoul elong
thermo_modify format float %.15g
min_style fire
minimize 1.0e-8 1.0e-8 5000 50000
timestep ${timestep}
velocity all create ${temperature} ${seed} dist gaussian
fix warm all nvt temp ${temperature} ${temperature} 100
run ${equilibration_steps}
unfix warm
fix ensemble all npt temp ${temperature} ${temperature} 100 iso ${pressure} ${pressure} 1000
run ${steps}
unfix ensemble
write_data equilibrated.data
# Replace model.in's read_data with a separately imported equilibrated.data case
# before property sampling; the original pet.data remains the packing state.
"""


def build(parameters, directory, packmol):
    values = validate_parameters(parameters)
    directory = Path(directory)
    packmol = Path(packmol).resolve(strict=True)
    if not packmol.is_file() or not os.access(packmol, os.X_OK):
        raise ValueError("Packmol must be an executable registered module program")
    # mBuild resolves Packmol from PATH; the parent has already whitelisted env.
    os.environ["PATH"] = str(packmol.parent) + os.pathsep + os.defpath
    directory.mkdir()  # New staging directory only.
    xml = forcefield_text()
    ff_path = directory / "forcefield.xml"
    ff_path.write_bytes(xml.encode("utf-8"))
    structure, validation, timings = typed_structure(values, ff_path, packmol=packmol)
    write_data(structure, directory / "pet.data")
    definition = profile()
    canonical = json.dumps(definition, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    hashes = {"profile_canonical_sha256": hashlib.sha256(canonical).hexdigest(),
              "forcefield_xml_sha256": hashlib.sha256(xml.encode("utf-8")).hexdigest()}
    data_path = directory / "pet.data"
    data = data_path.read_text(encoding="utf-8")
    first, rest = data.split("\n", 1)
    data_path.write_text(first + "\n# " + PROFILE_ID + "; DOI 10.3390/polym14061161\n"
                         + "# XML SHA256 " + hashes["forcefield_xml_sha256"] + "\n"
                         + "# Profile SHA256 " + hashes["profile_canonical_sha256"] + "\n"
                         + "# Tail OH published -0.566 -> -0.565 e; full profile in pet-model.json\n" + rest,
                         encoding="utf-8", newline="\n")
    (directory / "model.in").write_text(MODEL_IN, encoding="utf-8", newline="\n")
    (directory / "in.pet").write_text(PREPARATION_IN, encoding="utf-8", newline="\n")
    for name in ("tg", "modulus", "diffusion"):
        warning = "# This is a packing state; equilibrate and import an equilibrated case before properties.\n"
        if name == "diffusion":
            warning += "# PURE PET contains no penetrant. Selecting PET atoms does not measure gas diffusion/barrier.\n"
        (directory / ("in." + name)).write_text(warning + template_text(name), encoding="utf-8", newline="\n")
    manifest = {"format": "stk.pet-model/1", "profile_id": PROFILE_ID, "parameters": values,
                "chemistry": "Dry neutral linear COOH/OH PET; no penetrant", "validation": validation,
                "software": {name: version(name) for name in ("mbuild", "foyer", "parmed", "rdkit")},
                "packmol_sha256": hashlib.sha256(packmol.read_bytes()).hexdigest(),
                "timings_seconds": timings, "forcefield": definition, **hashes,
                "limitations": ["Initial packing is not an equilibrated amorphous sample.",
                                "DP4 is an oligomer; no validated Tg, modulus, gas D, solubility or permeability.",
                                "Independent annealing/cooling histories, chain lengths, seeds, finite-size and strain-rate convergence are required.",
                                "This PET-only model does not assign parameters to gases, ions or water."]}
    manifest["software"]["packmol"] = validation["packmol"]["version"]
    manifest["files"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.iterdir())}
    (directory / "pet-model.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                               encoding="utf-8", newline="\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Build dry neutral PET offline in the molecular-modeling module")
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--packmol", type=Path, required=True)
    args = parser.parse_args()
    manifest = build(json.loads(args.parameters.read_text(encoding="utf-8")), args.out, args.packmol)
    print(json.dumps({"profile_id": manifest["profile_id"], "validation": manifest["validation"]}, allow_nan=False))


if __name__ == "__main__":
    main()
