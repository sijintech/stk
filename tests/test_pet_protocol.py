"""Protocol boundaries, lineage choices and finite raw evidence, without MD."""
from copy import deepcopy
import hashlib
import json
import math

import pytest

from suan.lammps.pet_protocol import (FORMAT, MAX_DUMP_BYTES, MAX_FRAMES, OXYGEN_PROFILE, default_recipe,
                                     exact_forcefield_files, oxygen_profile,
                                     make_stage_files, model_text_for_data, stage_parameters,
                                     validate_recipe)
from suan.lammps.pet_worker import MODEL_IN
from suan.lammps.script import check_script, check_parameters


def test_complete_modes_are_distinct_frozen_starting_budgets():
    pilot, research = validate_recipe(), validate_recipe({"mode": "research"})
    assert pilot["format"] == research["format"] == FORMAT
    assert research["tg"]["steps"] > pilot["tg"]["steps"]
    assert research["model"]["chain_length"] == 20
    assert validate_recipe({"mode": "research", "model": {"seed": 42}})["model"]["chain_length"] == 20
    request = {"model": {"chain_length": 8, "chain_count": 10, "seed": 42},
               "diffusion": {"steps": 2000}}
    before = deepcopy(request)
    frozen = validate_recipe(request)
    assert request == before
    assert frozen["relax"]["seed"] == 42
    assert frozen["diffusion"]["time_max"] == 400
    frozen["model"]["seed"] = 1
    assert request == before


@pytest.mark.parametrize("proposal", [
    {"format": "future/2"}, {"mode": "converged"}, {"mode": []}, {"forcefield_profile": "new-pet"},
    {"unexpected": True}, {"model": {"chain_length": 21}},
    {"relax": {"temperature": float("nan")}}, {"relax": {"seed": True}},
    {"relax": {"seed": 2147483647}}, {"relax": {"steps": 2 ** 2000}},
    {"tg": {"temperatures": [600, 550, 500, 400, 350, 300, 350]}},
    {"tg": {"temperatures": [600, 550, 500]}}, {"tg": {"temperature": 300}},
    {"modulus": {"temperature": 299}}, {"modulus": {"strain_rate": 1e-12, "strain_min": .01}},
    {"modulus": {"strain_min": .02, "strain_max": .01}},
    {"diffusion": {"group": "oxygen"}}, {"diffusion": {"dimensions": True}},
    {"diffusion": {"solute_type": 1}}, {"diffusion": {"time_max": 10001}},
    {"diffusion": {"time_min": 0, "time_max": 10}},
    {"tg": {"sample_interval": 2000}}, {"tg": {"dump_interval": 1}},
    {"tg": {"dump_interval": 333}},
])
def test_invalid_or_misleading_recipes_fail_before_execution(proposal):
    with pytest.raises(ValueError):
        validate_recipe(proposal)


def test_trajectories_are_bounded_for_large_models_and_final_steps():
    recipe = validate_recipe({"mode": "research", "model": {"chain_length": 20, "chain_count": 100}})
    atoms = (22 * 20 + 3) * 100
    for stage in ("relax", "tg", "modulus", "diffusion"):
        config = recipe[stage]
        assert config["steps"] % config["dump_interval"] == 0
        frames = config["steps"] // config["dump_interval"] + 1
        assert 2 <= frames <= MAX_FRAMES
        assert frames * atoms * 180 <= MAX_DUMP_BYTES


def test_stages_use_existing_case_fields_and_separate_frozen_inputs_from_outputs():
    recipe = validate_recipe()
    original_hash = hashlib.sha256(MODEL_IN.encode()).hexdigest()
    for stage in ("relax", "tg", "modulus", "diffusion"):
        kwargs = {"temperature": 350} if stage == "tg" else {}
        files = make_stage_files(recipe, stage, MODEL_IN, original_data_text=_source_data(), **kwargs)
        text = files["in." + stage]
        checked = check_script(text, files=[*files, "input-state.data"], read=lambda name: files[name])
        params = stage_parameters(recipe, stage, **kwargs)
        assert checked["units"] == "real"
        assert checked["parameters"] == params
        assert check_parameters(params, checked["used"]) == params
        assert "read_data input-state.data\n" in files["model.in"]
        assert "write_data state.data\n" in text
        assert "id mol type q xu yu zu" in text
        assert "reset_timestep" not in text[text.index("dump trajectory "):]
        assert "dump_modify trajectory sort id first yes" in text
    assert hashlib.sha256(MODEL_IN.encode()).hexdigest() == original_hash


def test_cooling_inherits_velocities_and_actual_previous_temperature():
    recipe = validate_recipe()
    files = make_stage_files(recipe, "tg", MODEL_IN, temperature=350, original_data_text=_source_data())
    text = files["in.tg"]
    assert "fix cool all npt temp 400 ${temperature}" in text
    assert "velocity " not in text
    assert "seed" not in stage_parameters(recipe, "tg", temperature=350)
    with pytest.raises(ValueError, match="frozen cooling"):
        make_stage_files(recipe, "tg", MODEL_IN, temperature=345)
    with pytest.raises(ValueError, match="frozen recipe"):
        make_stage_files(recipe, "relax", MODEL_IN, seed=42)


def test_pet_com_msd_does_not_select_a_gas_atom_type_or_remove_each_chains_motion():
    text = make_stage_files(validate_recipe(), "diffusion", MODEL_IN, original_data_text=_source_data())["in.diffusion"]
    assert "chunk/atom molecule compress yes nchunk once ids once" in text
    assert "msd/chunk molecules" in text
    assert "ave(c_chain_msd[4])" in text
    assert 'title2 "Step Time MSD"' in text
    assert "solute_type" not in text and "com yes" not in text
    assert "not gas diffusion or permeability" in text
    assert "fix ensemble all nvt" in text
    assert "velocity " not in text


@pytest.mark.parametrize("data_name", ["state.data", "../pet.data", "/pet.data", "pet.data\nshell bad", "x.data # bad"])
def test_new_data_filename_cannot_overwrite_output_or_inject_commands(data_name):
    with pytest.raises(ValueError):
        model_text_for_data(MODEL_IN, data_name)


def test_model_rewrite_preserves_all_force_field_commands_and_rejects_ambiguous_reads():
    assert model_text_for_data(MODEL_IN) == MODEL_IN.replace("read_data pet.data", "read_data input-state.data")
    for text in (MODEL_IN + "read_data other.data\n", MODEL_IN.replace("read_data pet.data\n", ""),
                 MODEL_IN.replace("read_data pet.data", "read_data pet.data add append")):
        with pytest.raises(ValueError):
            model_text_for_data(text)


def _source_data():
    """Synthetic full-data records exercise insertion plumbing, not PET physics."""
    atoms = "\n".join(f"{i} 7 1 0.0 {i % 10} {(i // 10) % 10} 1" for i in range(1, 48))
    pairs = [(i, i + 1) for i in range(1, 47)] + [(1, 47), (1, 3)]
    bonds = "\n".join(f"{i} 1 {a} {b}" for i, (a, b) in enumerate(pairs, 1))
    return ("# Synthetic count/topology fixture\n\n47 atoms\n48 bonds\n1 atom types\n1 bond types\n"
            "0 20 xlo xhi\n0 20 ylo yhi\n0 20 zlo zhi\n\nMasses\n\n1 12.012\n\n"
            "Pair Coeffs\n\n1 .066 3.5\n\nBond Coeffs\n\n1 340 1.09\n\n"
            f"Atoms # full\n\n{atoms}\n\nBonds\n\n{bonds}\n")


def _saved_source_data(*, zero=False):
    velocities = "".join(f"{i} 0 0 0\n" if zero else
                         f"{i} {i * .001:.17g} {-i * .002:.17g} {i * .003:.17g}\n" for i in range(1, 48))
    return _source_data() + "\nVelocities\n\n" + velocities


def test_oxygen_table_conventions_preserve_potential_minimum_and_bond_energy():
    gas = oxygen_profile()
    assert gas["profile"] == OXYGEN_PROFILE
    assert gas["supplementary_license"] == "CC BY-NC 4.0"
    sigma, minimum = gas["lammps_LJ_sigma_A"], gas["paper_LJ_rmin_A"]
    epsilon = gas["LJ_epsilon_kcal_mol"]
    lj = lambda r: 4 * epsilon * ((sigma / r) ** 12 - (sigma / r) ** 6)
    assert math.isclose(sigma, 2.9372930737086986, abs_tol=1e-14)
    assert math.isclose(lj(minimum), -epsilon, abs_tol=1e-14)
    assert lj(sigma) == 0
    displacement = .1
    assert math.isclose(gas["lammps_harmonic_K_kcal_mol_A2"] * displacement ** 2,
                        .5 * gas["paper_bond_K_kcal_mol_A2"] * displacement ** 2)
    assert gas["charge_e"] == 0 and gas["mass_g_mol"] == 15.9994
    assert gas["physical_validation"] == "unresolved" and not gas["PET_O2_transport_validated"]
    assert gas["permeability"] == "not evaluated"


def test_oxygen_recipe_freezes_tracer_controls_and_never_silently_ignores_gas_options():
    recipe = validate_recipe({"model": {"seed": 42}, "diffusion": {"group": "o2_com"}})
    assert recipe["diffusion"]["gas_seed"] == 42
    assert recipe["diffusion"]["gas_count"] == 2
    assert recipe["diffusion"]["gas_profile"] == OXYGEN_PROFILE
    assert validate_recipe(recipe) == recipe
    for overrides in ({"gas_count": True}, {"gas_count": 0}, {"gas_count": 33}, {"gas_seed": 0},
                      {"gas_seed": 900000001}, {"gas_profile": "unknown/2"}, {"overlap_distance": 0},
                      {"insertion_attempts": 0}, {"group": []}):
        with pytest.raises(ValueError):
            validate_recipe({"diffusion": {"group": "o2_com", **overrides}})
    with pytest.raises(ValueError, match="Gas options"):
        validate_recipe({"diffusion": {"gas_count": 2}})
    with pytest.raises(ValueError, match="atom budget"):
        validate_recipe({"model": {"chain_length": 3, "chain_count": 724},
                         "diffusion": {"group": "o2_com", "gas_count": 32}})


def test_oxygen_insertion_reserves_actual_types_and_checks_counts_before_and_after_md():
    recipe = validate_recipe({"model": {"chain_length": 2, "chain_count": 1},
                              "diffusion": {"group": "o2_com", "gas_count": 3}})
    source = _saved_source_data()
    files = make_stage_files(recipe, "diffusion", MODEL_IN, state_data_text=source, original_data_text=source)
    metadata = json.loads(files["gas-model.json"])
    assert metadata["expected_atoms"] == 53 and metadata["expected_bonds"] == 51
    assert metadata["atom_type"] == metadata["bond_type"] == 2
    assert metadata["molecule_id_lower_bound"] == 8
    assert metadata["input_state_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert "extra/atom/types 1 extra/bond/types 1" in files["model.in"]
    assert "extra/bond/per/atom 1 extra/special/per/atom 1" in files["model.in"]
    text = files["in.diffusion"]
    assert "molecule oxygen oxygen.mol offset 1 1 0 0 0" in text
    assert "overlap 2.5 maxtry 10000 units box" in text
    assert "group gas type 2" in text and "group polymer type 1:1" in text
    assert text.count('if "$(count(gas)) != 6"') == 2
    assert text.count('if "$(count(all)) != 53"') == 2
    assert text.count('"quit 1"') == 4
    assert "compute molecules gas chunk/atom molecule compress yes nchunk once ids once" in text
    assert "compute gas_msd gas msd/chunk molecules" in text
    assert "chain_msd" not in text and "com yes" not in text
    assert "physical convergence unresolved" in text and "v_gas_atom_count" in text
    assert "velocity gas create" in text and "mom no rot no" in text
    assert "reset_timestep" not in text[text.index("dump trajectory "):]
    assert "Charges\n\n1 0.0\n2 0.0" in files["oxygen.mol"]
    assert "Bonds\n\n1 1 1 2" in files["oxygen.mol"]
    checked = check_script(text, files=[*files, "input-state.data"], read=files.__getitem__)
    assert checked["parameters"] == stage_parameters(recipe, "diffusion")


def test_gas_preparation_preserves_pet_velocities_and_thermal_state_instead_of_fire_quenching():
    from suan.lammps.script import commands
    # Explicit full velocity records distinguish retaining the handoff from
    # accidentally treating a geometry-only data file as a warm saved state.
    source = _saved_source_data()
    frozen_hash = hashlib.sha256(source.encode()).hexdigest()
    recipe = validate_recipe({"model": {"chain_length": 2, "chain_count": 1}, "diffusion": {"group": "o2_com"}})
    files = make_stage_files(recipe, "diffusion", MODEL_IN, state_data_text=source, original_data_text=_source_data())
    parsed = [words for _, words in commands(files["in.diffusion"])]
    assert not any(words[0] in {"min_style", "minimize"} for words in parsed)
    velocities = [words for words in parsed if words[0] == "velocity"]
    assert len(velocities) == 2
    assert velocities[0][:4] == ["velocity", "gas", "create", "${temperature}"]
    assert velocities[1] == ["velocity", "all", "zero", "linear"]
    assert not any(words[0] == "velocity" and words[1] in {"all", "polymer"}
                   and words[2] in {"create", "set", "scale"} for words in parsed)
    assert "read_data input-state.data extra/atom/types 1" in files["model.in"]
    assert "input-state.data" not in files  # the caller copies the original bytes, not a regenerated geometry
    assert hashlib.sha256(source.encode()).hexdigest() == frozen_hash
    metadata = json.loads(files["gas-model.json"])
    assert metadata["input_state_sha256"] == frozen_hash
    assert metadata["polymer_handoff"].startswith("retain source coordinates and velocities")


def test_oxygen_source_is_required_and_cannot_reinterpret_wrong_source_or_mixing():
    recipe = validate_recipe({"model": {"chain_length": 2, "chain_count": 1}, "diffusion": {"group": "o2_com"}})
    with pytest.raises(ValueError, match="frozen pure-PET"):
        make_stage_files(recipe, "diffusion", MODEL_IN)
    for source in (_saved_source_data().replace("47 atoms", "46 atoms"),
                   _saved_source_data().replace("1 7 1 0.0", "1 7 1 0.1"),
                   _saved_source_data().replace("47 atoms", "47 atoms\n47 atoms"),
                   _saved_source_data().replace("1 7 1 0.0", "1 8 1 0.0")):
        with pytest.raises(ValueError):
            make_stage_files(recipe, "diffusion", MODEL_IN, state_data_text=source, original_data_text=_source_data())
    with pytest.raises(ValueError, match="geometric OPLS"):
        make_stage_files(recipe, "diffusion", MODEL_IN.replace("mix geometric", "mix arithmetic"),
                         state_data_text=_saved_source_data(), original_data_text=_source_data())
    # Service can pass the same optional argument for every stage.
    assert "oxygen.mol" not in make_stage_files(recipe, "relax", MODEL_IN, state_data_text="unused")


@pytest.mark.parametrize("source", [_source_data(), "\n".join(_saved_source_data().splitlines()[:-1]) + "\n"])
def test_o2_rejects_geometry_only_or_partial_velocity_handoff_before_generating_inputs(source):
    recipe = validate_recipe({"model": {"chain_length": 2, "chain_count": 1}, "diffusion": {"group": "o2_com"}})
    with pytest.raises(ValueError, match="complete saved PET velocities"):
        make_stage_files(recipe, "diffusion", MODEL_IN, state_data_text=source, original_data_text=_source_data())


def test_complete_zero_velocities_are_retained_without_inventing_a_warm_state():
    recipe = validate_recipe({"model": {"chain_length": 2, "chain_count": 1}, "diffusion": {"group": "o2_com"}})
    source = _saved_source_data(zero=True)
    files = make_stage_files(recipe, "diffusion", MODEL_IN, state_data_text=source, original_data_text=_source_data())
    assert json.loads(files["gas-model.json"])["input_state_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert "velocity all create" not in files["in.diffusion"]
    assert "minimize" not in files["in.diffusion"]


def _coefficient_source():
    # Explicit coefficient records with roundoff-sensitive values and no fake
    # claim of material validation. The fixture is a table serialization test.
    source = _source_data().replace("1 bond types", "1 bond types\n1 angle types\n1 dihedral types\n1 improper types")
    return source + ("\nAngle Coeffs\n\n1 37.500000000000007 110.70000000000002\n\n"
                     "Dihedral Coeffs\n\n1 4.318996175908222 0 0.4679995219885277 2.390057361134623e-6\n\n"
                     "Improper Coeffs\n\n1 2.5000000000000004 -1 2\n")


def test_exact_companion_restores_original_double_values_with_correct_command_arities():
    from suan.lammps.script import commands
    from suan.lammps.structure import parse_data
    source = _coefficient_source()
    topology = parse_data(source)
    files = exact_forcefield_files(source)
    document = json.loads(files["forcefield-exact.json"])
    assert document["source_data_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert document["commands_sha256"] == hashlib.sha256(files["forcefield-exact.in"].encode()).hexdigest()
    expected_sections = {"pair": "Pair Coeffs", "bond": "Bond Coeffs", "angle": "Angle Coeffs",
                         "dihedral": "Dihedral Coeffs", "improper": "Improper Coeffs"}
    for _, words in commands(files["forcefield-exact.in"]):
        kind = words[0].removesuffix("_coeff")
        identity = int(words[1])
        first = 3 if kind == "pair" else 2
        assert tuple(map(float, words[first:])) == topology.coefficients[expected_sections[kind]][identity]
        if kind == "pair":
            assert words[1] == words[2]
        if kind == "improper":
            assert words[-2:] == ["-1", "2"]
    assert float("4.319") != topology.coefficients["Dihedral Coeffs"][1][0]
    assert float("2.39006e-6") != topology.coefficients["Dihedral Coeffs"][1][3]
    assert len(document["tables"]) == 5


def test_downstream_restoration_follows_read_data_and_never_changes_relaxation_bytes():
    recipe, original = validate_recipe(), _coefficient_source()
    before = make_stage_files(recipe, "relax", MODEL_IN)
    assert make_stage_files(recipe, "relax", MODEL_IN, original_data_text=original) == before
    assert make_stage_files(recipe, "relax", MODEL_IN, original_data_text="ignored") == before
    for stage, kwargs in (("tg", {"temperature": 350}), ("modulus", {}), ("diffusion", {})):
        files = make_stage_files(recipe, stage, MODEL_IN, original_data_text=original, **kwargs)
        model_lines = files["model.in"].splitlines()
        position = model_lines.index("read_data input-state.data")
        assert model_lines[position + 1] == "include forcefield-exact.in"
        assert files["forcefield-exact.in"] == exact_forcefield_files(original)["forcefield-exact.in"]
        with pytest.raises(ValueError, match="first frozen model"):
            make_stage_files(recipe, stage, MODEL_IN, **kwargs)


@pytest.mark.parametrize("mutate", [
    lambda source: source.replace("Dihedral Coeffs", "Unknown Coeffs"),
    lambda source: source.replace("4.318996175908222 0 0.4679995219885277 2.390057361134623e-6", "4.319 0 .468"),
    lambda source: source.replace("-1 2", "-1 2.5"),
    lambda source: source.replace("-1 2", "3 2"),
    lambda source: source.replace("1 dihedral types", "2 dihedral types"),
    lambda source: source.replace("4.318996175908222", "nan"),
])
def test_restoration_refuses_incomplete_nonfinite_or_unsupported_tables(mutate):
    with pytest.raises(ValueError):
        exact_forcefield_files(mutate(_coefficient_source()))
