"""Independent, standard-library checks of the shipped PET parameter profile.

These tests build a chemical bond graph directly (no RDKit/mBuild/Foyer),
enumerate its physical term classes, and compare resource units to source tables.
"""
from collections import Counter
from decimal import Decimal
from itertools import combinations
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from suan.lammps.pet import (DEFAULT_PARAMETERS, FORCEFIELD, OUTPUTS, PROFILE, PROFILE_ID,
                             MAX_CHAIN_LENGTH, expected_types, forcefield_text, profile, validate_parameters)


def topology(length):
    """Explicit HOOC–para-phenylene–COO–CH2–CH2 segments with one OH tail."""
    labels, neighbors = [], []

    def atom(kind):
        labels.append(kind)
        neighbors.append(set())
        return len(labels) - 1

    def bond(a, b):
        neighbors[a].add(b)
        neighbors[b].add(a)

    def attached(parent, kind):
        child = atom(kind)
        bond(parent, child)
        return child

    bridge = None
    for repeat in range(length):
        ring = [atom("PET_CA") for _ in range(6)]
        for index, carbon in enumerate(ring):
            bond(carbon, ring[(index + 1) % 6])
        for index in (1, 2, 4, 5):
            attached(ring[index], "PET_HA")
        left = attached(ring[0], "PET_CO_ACID" if repeat == 0 else "PET_CO_ESTER")
        attached(left, "PET_O_ACID" if repeat == 0 else "PET_O_ESTER")
        if repeat == 0:
            acid_oxygen = attached(left, "PET_OH_ACID")
            attached(acid_oxygen, "PET_HO_ACID")
        else:
            bond(left, bridge)
        right = attached(ring[3], "PET_CO_ESTER")
        attached(right, "PET_O_ESTER")
        oxygen = attached(right, "PET_OES")
        first = attached(oxygen, "PET_CT_ESTER")
        attached(first, "PET_HAE")
        attached(first, "PET_HAE")
        last = repeat == length - 1
        second = attached(first, "PET_CT_OH" if last else "PET_CT_ESTER")
        for _ in range(2):
            attached(second, "PET_HC_OH" if last else "PET_HAE")
        bridge = attached(second, "PET_OH_TAIL" if last else "PET_OES")
        if last:
            attached(bridge, "PET_HO_TAIL")
    return labels, neighbors


def canonical(types):
    values = tuple(types)
    return min(values, values[::-1])


def terms(labels, neighbors, atom_types):
    classes = [atom_types[name]["class"] for name in labels]
    found = {"bond": set(), "angle": set(), "proper": set()}
    for a, around in enumerate(neighbors):
        for b in around:
            if a >= b:
                continue
            found["bond"].add(canonical((classes[a], classes[b])))
            for i in around - {b}:
                for j in neighbors[b] - {a, i}:
                    found["proper"].add(canonical((classes[i], classes[a], classes[b], classes[j])))
        for a1, a2 in combinations(around, 2):
            found["angle"].add(canonical((classes[a1], classes[a], classes[a2])))
    return found


def test_profile_resources_are_shipped_and_import_without_molecular_packages(tmp_path):
    from importlib.resources import files
    package = files("suan.lammps").joinpath("forcefields")
    assert package.joinpath(PROFILE).is_file() and package.joinpath(FORCEFIELD).is_file()
    source = (
        "import importlib.abc,sys; sys.path.insert(0,sys.argv[1]); "
        "exec(\"class Refuse(importlib.abc.MetaPathFinder):\\n"
        " def find_spec(self,fullname,path=None,target=None):\\n"
        "  if fullname.split('.')[0] in {'mbuild','foyer','parmed','rdkit','gmso','numpy'}:"
        " raise RuntimeError('optional molecular import: '+fullname)\\n\"); "
        "sys.meta_path.insert(0,Refuse()); "
        "from suan.lammps.pet import profile,forcefield_text; "
        "assert profile()['id']=='stk.pet.opls-mk2022/1'; assert '<ForceField' in forcefield_text()"
    )
    result = subprocess.run([sys.executable, "-I", "-c", source, str(Path(__file__).resolve().parents[1])],
                            cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("length", [2, 3, 4, 8, 100])
def test_formula_type_counts_and_complete_chain_charges_match_independent_chemistry(length):
    definition = profile()
    types = {item["name"]: item for item in definition["atom_types"]}
    labels, _ = topology(length)
    assert len(labels) == 22 * length + 3
    assert Counter(types[name]["element"] for name in labels) == {"C": 10 * length, "H": 8 * length + 2, "O": 4 * length + 1}
    assert Counter(labels) == expected_types(length)
    assert sum((Decimal(str(types[name]["charge_e"])) for name in labels), Decimal(0)) == 0
    assert Counter(labels)["PET_OH_TAIL"] == 1
    assert types["PET_CA"]["charge_e"] == -0.115


def test_published_trimer_rounding_residual_is_corrected_only_on_unique_tail_oxygen():
    definition = profile()
    published = definition["published_S1"]
    assert {part: len(atoms) for part, atoms in published.items()} == {"head": 23, "body": 22, "tail": 24}
    totals = {part: sum((Decimal(str(item[2])) for item in atoms), Decimal(0)) for part, atoms in published.items()}
    assert totals == {"head": Decimal("0.250"), "body": Decimal("0.000"), "tail": Decimal("-0.251")}
    correction = definition["charge_rounding_correction"]
    assert correction["type"] == "PET_OH_TAIL"
    assert Decimal(str(correction["effective_charge_e"])) - Decimal(str(correction["published_charge_e"])) == Decimal("0.001")
    assert sum(totals.values()) + Decimal(str(correction["delta_e"])) == 0


def test_xml_nonbonded_units_masses_and_type_definitions_match_complete_profile():
    definition, xml = profile(), ET.fromstring(forcefield_text())
    assert definition["id"] == PROFILE_ID and xml.attrib["combining_rule"] == "geometric"
    named = {item["name"]: item for item in definition["atom_types"]}
    xml_types = {item.attrib["name"]: item.attrib for item in xml.find("AtomTypes")}
    nonbonded = xml.find("NonbondedForce")
    assert float(nonbonded.attrib["coulomb14scale"]) == 0.5
    assert float(nonbonded.attrib["lj14scale"]) == 0.5
    xml_atoms = {item.attrib["type"]: item.attrib for item in nonbonded}
    assert len(named) == len(definition["atom_types"]) == 15
    assert set(xml_types) == set(xml_atoms) == set(named)
    for name, atom in named.items():
        actual_type, actual = xml_types[name], xml_atoms[name]
        sigma, epsilon, mass = atom["lj_sigma_A_epsilon_kcal_mass"]
        assert (actual_type["class"], actual_type["element"], actual_type["def"]) == (atom["class"], atom["element"], atom["smarts"])
        assert float(actual_type["mass"]) == mass
        assert float(actual["charge"]) == atom["charge_e"]
        assert float(actual["sigma"]) == pytest.approx(sigma / 10, abs=1e-14)
        assert float(actual["epsilon"]) == pytest.approx(epsilon * 4.184, abs=1e-14)


@pytest.mark.parametrize("length", [2, 3, 4, 8])
def test_every_physical_bond_angle_and_proper_term_has_one_explicit_parameter(length):
    definition, xml = profile(), ET.fromstring(forcefield_text())
    atom_types = {item["name"]: item for item in definition["atom_types"]}
    labels, neighbors = topology(length)
    needed = terms(labels, neighbors, atom_types)
    sections = {"bond": ("HarmonicBondForce", "Bond", 2), "angle": ("HarmonicAngleForce", "Angle", 3),
                "proper": ("RBTorsionForce", "Proper", 4)}
    for kind, (section, entry, count) in sections.items():
        listed = [canonical(term["types"]) for term in definition["terms"][kind]]
        encoded = [canonical(term.attrib[f"class{i}"] for i in range(1, count + 1)) for term in xml.find(section).findall(entry)]
        assert len(listed) == len(set(listed)), f"ambiguous {kind} profile entries"
        assert len(encoded) == len(set(encoded)), f"ambiguous {kind} XML entries"
        assert set(listed) == set(encoded) == needed[kind], f"missing or irrelevant {kind} types"
    sp2 = sum(atom_types[name]["class"] in ("CA", "CO") for name in labels)
    assert sp2 == 8 * length
    assert xml.find("PeriodicTorsionForce") is None  # Worker supplies source-ordered impropers separately.


@pytest.mark.parametrize("kind,section,entry", [("bond", "HarmonicBondForce", "Bond"),
                                               ("angle", "HarmonicAngleForce", "Angle"),
                                               ("proper", "RBTorsionForce", "Proper")])
def test_xml_bonded_units_and_torsion_energies_match_recorded_source_equations(kind, section, entry):
    definition, xml = profile(), ET.fromstring(forcefield_text())
    count = {"bond": 2, "angle": 3, "proper": 4}[kind]
    encoded = {canonical(term.attrib[f"class{i}"] for i in range(1, count + 1)): term.attrib
               for term in xml.find(section).findall(entry)}
    for term in definition["terms"][kind]:
        actual = encoded[canonical(term["types"])]
        origin = term["origin"]
        source = origin["source_parameters"]
        published = origin["source"] == "polymers-2022-supplement"
        assert origin["source"] in {"polymers-2022-supplement", "gromacs-v2025.3-oplsaa"}
        if kind == "bond":
            length = source[1] / 10 if published else source[0]
            stiffness = source[0] * 4.184 * 100 if published else source[1]
            assert float(actual["length"]) == pytest.approx(length, abs=1e-14)
            assert float(actual["k"]) == pytest.approx(stiffness, rel=1e-14)
        elif kind == "angle":
            angle = math.radians(source[1] if published else source[0])
            stiffness = source[0] * 4.184 if published else source[1]
            assert float(actual["angle"]) == pytest.approx(angle, abs=1e-14)
            assert float(actual["k"]) == pytest.approx(stiffness, rel=1e-14)
        else:
            coefficients = [float(actual[f"c{i}"]) for i in range(6)]
            for phi in (-math.pi, -2.31, -0.73, 0, 1.18, math.pi):
                rb_energy = math.fsum(c * math.cos(phi - math.pi) ** i for i, c in enumerate(coefficients)) / 4.184
                if published:
                    a1, a2, a3 = source
                    expected = (a1 * (1 + math.cos(phi)) + a2 * (1 - math.cos(2 * phi)) + a3 * (1 + math.cos(3 * phi))) / 2
                else:
                    expected = math.fsum(c * math.cos(phi - math.pi) ** i for i, c in enumerate(source)) / 4.184
                assert rb_energy == pytest.approx(expected, abs=1e-11)


def test_improper_conversion_and_pinned_source_evidence_are_complete():
    definition = profile()
    assert definition["bonded_only_aliases"] == {"CO": "C", "OES": "OS", "HAE": "HC"}
    for kind in ("carbonyl", "aromatic"):
        improper = definition["impropers"][kind]
        phase, amplitude, periodicity = improper["source_parameters"]
        assert phase == 180 and periodicity == 2
        assert improper["phi_k_kcal_mol"] == pytest.approx(amplitude / 4.184, abs=1e-13)
        assert improper["cvff"] == [improper["phi_k_kcal_mol"], -1, 2]
        assert improper["source_line_number"] > 0
    assert definition["sources"]["published"]["doi"] == "10.3390/polym14061161"
    for source in definition["sources"].values():
        assert source["license"] and source["url"].startswith("https://")
        digests = [value for key, value in source.items() if key.endswith("sha256")]
        assert digests and all(re.fullmatch(r"[0-9a-f]{64}", value) for value in digests)
    canonical_source = definition["sources"]["canonical"]
    assert "/v2025.3/" in canonical_source["url"]


def test_default_model_is_546_atoms_and_profile_json_is_finite():
    values = validate_parameters(DEFAULT_PARAMETERS)
    assert (22 * values["chain_length"] + 3) * values["chain_count"] == 546
    assert OUTPUTS == ("pet.data", "model.in", "forcefield.xml", "pet-model.json", "in.pet", "in.tg", "in.modulus", "in.diffusion")
    assert json.loads(json.dumps(profile(), allow_nan=False)) == profile()


def test_whole_chain_geometry_limit_rejects_large_input_before_optional_imports():
    assert MAX_CHAIN_LENGTH == 20
    assert validate_parameters({"chain_length": 20})["chain_length"] == 20
    with pytest.raises(ValueError, match="chain_length"):
        validate_parameters({"chain_length": 21})
