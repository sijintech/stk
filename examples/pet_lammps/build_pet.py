"""Build an amorphous PET box with mBuild + Packmol, type it with foyer's OPLS-AA plus the STK patch, write a LAMMPS data file.

Feasibility script for E1 (docs/design/multiscale-engines.md), not product code. Run it with the Python of the
molecular-modelling module (mBuild, foyer, GMSO, RDKit) with Packmol on PATH, for example:

    ~/.stk/modules/envs/molecular-modeling/bin/python build_pet.py --chains 6 --out acceptance/pet-case/pet.data

The ring-carbon 0.0 patch is a historical feasibility inference, not the selected product forcefield.
The literature-backed COOH/OH PET profile is in suan/lammps/pet.py and examples/pet_model;
this different 540-atom OH/CHO fixture remains only for writer comparison. Do not report its material properties.
"""
from pathlib import Path
import argparse
import os
import sys
import tempfile
import time
import warnings
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
PATCH = HERE / "pet-oplsaa-patch.xml"
# One repeat unit with a hydroxyl and an aldehyde H as the two ports that mBuild's Polymer replaces when chaining.
REPEAT_UNIT = "OCCOC(=O)c1ccc(cc1)C=O"


def merged_forcefield(out, patch=PATCH):
    """foyer's OPLS-AA with the STK patch merged in, section by section (foyer validates each file on its own, so a
    separate patch file cannot refer to the types of oplsaa.xml)."""
    import foyer
    base = ET.parse(Path(foyer.__file__).parent / "forcefields" / "xml" / "oplsaa.xml")
    root = base.getroot()
    for section in ET.parse(patch).getroot():
        target = root.find(section.tag)
        if target is None:
            root.append(section)
        else:
            target.extend(list(section))
    base.write(out)
    return out


def chain(repeats=4):
    import mbuild as mb
    from mbuild.lib.recipes import Polymer
    unit = mb.load(REPEAT_UNIT, smiles=True)
    bonds = {}
    for a, b in unit.bonds():
        bonds.setdefault(a, []).append(b)
        bonds.setdefault(b, []).append(a)
    parts = list(unit.particles())
    hydroxyl = next(i for i, p in enumerate(parts) if p.name == "H" and bonds[p][0].name == "O")
    aldehyde = next(i for i, p in enumerate(parts) if p.name == "H" and bonds[p][0].name == "C"
                    and sum(1 for n in bonds[bonds[p][0]] if n.name == "O") == 1 and len(bonds[bonds[p][0]]) == 3)
    polymer = Polymer()
    polymer.add_monomer(compound=unit, indices=[hydroxyl, aldehyde], separation=0.14, replace=True)
    polymer.build(n=repeats, add_hydrogens=True)
    return polymer


def typed_structure(chains=6, repeats=4, density=250.0):
    """Historical feasibility fixture, including the historical charge patch."""
    import foyer
    import mbuild as mb
    timings, t = {}, time.time()
    box = mb.fill_box(compound=chain(repeats), n_compounds=chains, density=density)
    timings["pack"], t = time.time() - t, time.time()
    with tempfile.TemporaryDirectory() as work:  # not next to the data file, which becomes a case folder
        ff = foyer.Forcefield(forcefield_files=[merged_forcefield(Path(work) / "oplsaa-stk.xml")])
    structure = ff.apply(box)
    timings["apply"], t = time.time() - t, time.time()
    return structure, timings


def build(chains, repeats, density, out):
    """Returns timings; density is kg/m3. This remains the GMSO reference path."""
    from gmso.external import from_parmed
    from gmso.formats.lammpsdata import write_lammpsdata
    structure, timings = typed_structure(chains, repeats, density)
    t = time.time()
    topology = from_parmed(structure)
    timings["from_parmed"], t = time.time() - t, time.time()
    write_lammpsdata(topology, str(out), atom_style="full", unit_style="real")
    timings["gmso_write"] = time.time() - t
    charge = sum(a.charge for a in structure.atoms)
    print(f"atoms {len(structure.atoms)} bonds {len(structure.bonds)} angles {len(structure.angles)} "
          f"torsions {len(structure.rb_torsions) + len(structure.dihedrals)} net charge {charge:.4f}")
    print(" ".join(f"{k} {v:.1f}s" for k, v in timings.items()), flush=True)
    return timings


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chains", type=int, default=6)
    parser.add_argument("--repeats", type=int, default=4)
    parser.add_argument("--density", type=float, default=250.0, help="packing density in kg/m3")
    parser.add_argument("--out", type=Path, default=Path("pet.data"))
    args = parser.parse_args()
    warnings.filterwarnings("ignore")
    # Packmol and the other module programs sit next to the module's Python.
    os.environ["PATH"] = os.path.dirname(sys.executable) + os.pathsep + os.environ["PATH"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    build(args.chains, args.repeats, args.density, args.out)


if __name__ == "__main__":
    main()
