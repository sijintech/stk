"""Versioned dry PET study recipes and stage scripts, without executing a solver.

The existing PET force field and published property templates are unchanged.
Pilot durations exercise software paths; research durations are starting budgets,
not an equilibration, uncertainty, or bulk-material validation certificate.
"""
from copy import deepcopy
from collections import Counter
import hashlib
import json
import math
import re

from .pet import MAX_ATOMS, PROFILE_ID, validate_parameters

FORMAT = "stk.pet-study-recipe/1"
STAGES = ("relax", "tg", "modulus", "diffusion")
STATE = "state.data"
TRAJECTORY = "trajectory.dump"
MAX_FRAMES = 128
MAX_DUMP_BYTES = 128 * 1024 * 1024
MAX_SAMPLES = 100000
OXYGEN_PROFILE = "stk.oxygen.iff2021-12-6/1"
_GAS_FIELDS = {"gas_count", "gas_seed", "gas_profile", "overlap_distance", "insertion_attempts"}
_COMMON = {"temperature", "pressure", "timestep", "equilibration_steps", "steps", "sample_interval", "dump_interval"}
_EXTRA = {"relax": {"seed", "warmup_steps", "compression_steps", "compression_pressure"},
          "tg": {"temperatures"}, "modulus": {"strain_rate", "strain_min", "strain_max"},
          "diffusion": {"group", "time_min", "time_max", "dimensions", *_GAS_FIELDS}}


def oxygen_profile():
    """Minimal published numerical facts and their explicit real-unit adaptation.

    No supplementary force-field file is redistributed. Its CC BY-NC 4.0 license
    is source metadata, not a declaration of permission for every downstream use.
    This compatible mixing choice has not been validated for PET/O2 transport.
    """
    return {"profile": OXYGEN_PROFILE, "source_doi": "10.1021/acs.jctc.0c01132",
            "source_url": "https://par.nsf.gov/servlets/purl/10297174", "source_table": "Table 2, 12-6 O2",
            "supplementary_url": "https://acs.figshare.com/articles/journal_contribution/14977419",
            "supplementary_license": "CC BY-NC 4.0",
            "supplementary_sha256": "542c793b9bdadfab894eb45c913435bce1f47ad30fe031987d6da0f821ed52fc",
            "mass_source": "author supplementary cvff_interface_Gas.frc, o2g atom type",
            "charge_source": "author supplementary O2.car and O2.mdf, both oxygen charges zero",
            "units": "real", "mass_g_mol": 15.9994, "charge_e": 0.0,
            "bond_length_A": 1.2074, "paper_bond_K_kcal_mol_A2": 1640.4,
            "lammps_harmonic_K_kcal_mol_A2": 1640.4 / 2,
            "paper_LJ_rmin_A": 3.297, "lammps_LJ_sigma_A": 3.297 / 2 ** (1 / 6),
            "LJ_epsilon_kcal_mol": .1047, "cross_mixing": "geometric sigma and epsilon",
            "adaptations": ["paper rmin / 2^(1/6) gives LAMMPS zero-crossing sigma",
                            "paper half-prefactor harmonic Kr / 2 gives LAMMPS harmonic K",
                            "exact table conversion differs from author example's rounded sigma 2.937"],
            "scope": "neutral, nonreactive two-site harmonic O2 tracer; no quadrupole or polarization",
            "physical_validation": "unresolved", "PET_O2_transport_validated": False,
            "permeability": "not evaluated"}


def _number(value, name, minimum, maximum, *, integer=False):
    if (type(value) not in ((int,) if integer else (int, float)) or not minimum <= value <= maximum
            or not math.isfinite(value)):
        raise ValueError(f"{name} must be a finite {'integer' if integer else 'number'} in [{minimum}, {maximum}]")
    return value


def _interval(steps, atoms):
    """Choose an exact divisor so the bounded dump includes the final state."""
    frames = min(MAX_FRAMES, MAX_DUMP_BYTES // (atoms * 180))
    if frames < 2:
        raise ValueError("The model cannot fit two bounded trajectory frames")
    minimum = math.ceil(steps / (frames - 1))
    candidates = []
    for divisor in range(1, math.isqrt(steps) + 1):
        if steps % divisor == 0:
            candidates.extend((divisor, steps // divisor))
    return min(value for value in candidates if value >= minimum)


def default_recipe(mode="pilot"):
    """A complete recipe; callers can replace defaults before explicit preparation."""
    if type(mode) is not str or mode not in {"pilot", "research"}:
        raise ValueError("PET study mode must be pilot or research")
    research = mode == "research"
    model = validate_parameters({"chain_length": 20, "chain_count": 16} if research else {})
    common = {"pressure": 1.0, "timestep": 0.25, "sample_interval": 10000 if research else 100}
    recipe = {"format": FORMAT, "mode": mode, "forcefield_profile": PROFILE_ID, "model": model,
              "relax": {**common, "temperature": 600.0, "seed": model["seed"],
                        "warmup_steps": 80000 if research else 2000,
                        "compression_pressure": 250.0, "compression_steps": 8000000 if research else 8000,
                        "equilibration_steps": 8000000 if research else 8000,
                        "steps": 8000000 if research else 8000},
              "tg": {**common, "temperatures": [600., 550., 500., 450., 400., 350., 300., 250.],
                     "equilibration_steps": 8000000 if research else 2000,
                     "steps": 192000000 if research else 4000},
              "modulus": {**common, "temperature": 300.0,
                          "equilibration_steps": 8000000 if research else 2000,
                          "steps": 400000 if research else 4000, "strain_min": 0.0, "strain_max": 0.02},
              "diffusion": {**common, "temperature": 600.0, "group": "pet_chain_com", "dimensions": 3,
                            "equilibration_steps": 8000000 if research else 2000,
                            "steps": 400000000 if research else 40000}}
    atoms = (22 * model["chain_length"] + 3) * model["chain_count"]
    for stage in STAGES:
        config = recipe[stage]
        config["dump_interval"] = _interval(config["steps"], atoms)
    recipe["modulus"]["strain_rate"] = recipe["modulus"]["strain_max"] / (recipe["modulus"]["steps"] * common["timestep"])
    duration = recipe["diffusion"]["steps"] * common["timestep"]
    recipe["diffusion"].update(time_min=0.2 * duration, time_max=0.8 * duration)
    return recipe


def validate_recipe(recipe=None):
    """Expand a partial JSON recipe, reject unknown fields, and freeze finite values.

    Timing and sample bounds are software safeguards. Longer runs, the research
    label, or a fitted slope alone never establish material convergence.
    """
    if recipe is None:
        recipe = {}
    if type(recipe) is not dict:
        raise ValueError("PET study recipe must be an object")
    try:
        json.dumps(recipe, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("PET study recipe must contain finite plain JSON values") from error
    if set(recipe) - {"format", "mode", "forcefield_profile", "model", *STAGES}:
        raise ValueError("Unknown PET study recipe fields")
    base = default_recipe(recipe.get("mode", "pilot"))
    if recipe.get("format", FORMAT) != FORMAT or recipe.get("forcefield_profile", PROFILE_ID) != PROFILE_ID:
        raise ValueError("Unsupported PET study recipe or force field version")
    model = recipe.get("model", {})
    if type(model) is not dict:
        raise ValueError("PET model parameters must be an object")
    base["model"] = validate_parameters({**base["model"], **model})
    atoms = (22 * base["model"]["chain_length"] + 3) * base["model"]["chain_count"]
    for stage in STAGES:
        supplied = recipe.get(stage, {})
        allowed = (_COMMON - {"temperature"} if stage == "tg" else _COMMON) | _EXTRA[stage]
        if type(supplied) is not dict or set(supplied) - allowed:
            raise ValueError(f"Unknown {stage} protocol fields")
        config = base[stage]
        config.update(deepcopy(supplied))
        stage_atoms = atoms
        if stage == "diffusion":
            if type(config["group"]) is not str or config["group"] not in {"pet_chain_com", "o2_com"}:
                raise ValueError("Protocol 1 supports PET-chain COM or the explicitly sourced O2 tracer COM")
            if config["group"] == "o2_com":
                defaults = {"gas_count": 2, "gas_seed": base["model"]["seed"], "gas_profile": OXYGEN_PROFILE,
                            "overlap_distance": 2.5, "insertion_attempts": 10000}
                config.update({key: supplied.get(key, value) for key, value in defaults.items()})
                _number(config["gas_count"], "diffusion.gas_count", 1, 32, integer=True)
                # Molecule orientations use LAMMPS RanMars(seed + MPI rank),
                # whose limit is narrower than the PET builder's integer seed.
                # The service additionally checks the frozen rank allocation.
                _number(config["gas_seed"], "diffusion.gas_seed", 1, 900000000, integer=True)
                _number(config["overlap_distance"], "diffusion.overlap_distance", 1.5, 100)
                _number(config["insertion_attempts"], "diffusion.insertion_attempts", 1, 100000, integer=True)
                if config["gas_profile"] != OXYGEN_PROFILE:
                    raise ValueError("Unsupported O2 force-field version")
                stage_atoms += 2 * config["gas_count"]
                if stage_atoms > MAX_ATOMS:
                    raise ValueError("PET plus O2 exceeds the bounded atom budget")
            elif set(supplied) & _GAS_FIELDS:
                raise ValueError("Gas options require the O2 tracer group")
        for name in ("steps", "equilibration_steps", "sample_interval"):
            _number(config[name], f"{stage}.{name}", 1, 1000000000, integer=True)
        _number(config["timestep"], f"{stage}.timestep", 0.001, 1.0)
        _number(config["pressure"], f"{stage}.pressure", 0.001, 10000)
        if stage != "tg":
            _number(config["temperature"], f"{stage}.temperature", 100, 1000)
        if config["steps"] < 3 * config["sample_interval"] or config["steps"] // config["sample_interval"] > MAX_SAMPLES:
            raise ValueError(f"{stage} production must contain 3–{MAX_SAMPLES} samples")
        if "dump_interval" not in supplied:
            config["dump_interval"] = _interval(config["steps"], stage_atoms)
        _number(config["dump_interval"], f"{stage}.dump_interval", 1, config["steps"], integer=True)
        frames = config["steps"] // config["dump_interval"] + 1
        if (config["steps"] % config["dump_interval"] or frames > MAX_FRAMES
                or frames * stage_atoms * 180 > MAX_DUMP_BYTES):
            raise ValueError(f"{stage} dump must include the final step within the trajectory budget")
    relax = base["relax"]
    if "seed" not in recipe.get("relax", {}):
        relax["seed"] = base["model"]["seed"]
    # Park/Miller's modulus itself collapses to zero and its Gaussian loop can
    # hang. Keep the published PET builder unchanged, but refuse that MD seed.
    _number(relax["seed"], "relax.seed", 1, 2147483646, integer=True)
    for name in ("warmup_steps", "compression_steps"):
        _number(relax[name], f"relax.{name}", 1, 1000000000, integer=True)
    _number(relax["compression_pressure"], "relax.compression_pressure", relax["pressure"], 10000)
    temperatures = base["tg"]["temperatures"]
    if type(temperatures) is not list or not 6 <= len(temperatures) <= 32:
        raise ValueError("Tg needs 6–32 explicitly ordered temperatures")
    for value in temperatures:
        _number(value, "tg.temperatures", 100, 1000)
    if any(a <= b for a, b in zip(temperatures, temperatures[1:])) or temperatures[0] != relax["temperature"]:
        raise ValueError("Tg temperatures must descend strictly from the relaxation temperature")
    for stage in ("modulus", "diffusion"):
        if base[stage]["temperature"] not in temperatures:
            raise ValueError(f"{stage} temperature must have an explicitly saved cooling state")
    mod = base["modulus"]
    _number(mod["strain_min"], "modulus.strain_min", 0, 0.05)
    _number(mod["strain_max"], "modulus.strain_max", 0, 0.05)
    if mod["strain_max"] <= mod["strain_min"]:
        raise ValueError("The modulus fit window must increase")
    if "strain_rate" not in recipe.get("modulus", {}):
        mod["strain_rate"] = mod["strain_max"] / (mod["steps"] * mod["timestep"])
    _number(mod["strain_rate"], "modulus.strain_rate", 1e-12, 0.01)
    increment = mod["sample_interval"] * mod["timestep"] * mod["strain_rate"]
    low = max(1, math.ceil(mod["strain_min"] / increment))
    high = min(mod["steps"] // mod["sample_interval"], math.floor(mod["strain_max"] / increment + 1e-10))
    if high - low + 1 < 3:
        raise ValueError("The modulus fit window must contain at least three produced samples")
    diffusion = base["diffusion"]
    if type(diffusion["dimensions"]) is not int or diffusion["dimensions"] != 3:
        raise ValueError("Protocol 1 supports only explicitly three-dimensional molecular COM MSD")
    duration = diffusion["steps"] * diffusion["timestep"]
    supplied = recipe.get("diffusion", {})
    for name, fraction in (("time_min", .2), ("time_max", .8)):
        if name not in supplied:
            diffusion[name] = fraction * duration
        _number(diffusion[name], f"diffusion.{name}", 0, duration)
    if diffusion["time_max"] <= diffusion["time_min"]:
        raise ValueError("The MSD fit window must increase")
    interval = diffusion["sample_interval"] * diffusion["timestep"]
    low = max(1, math.ceil(diffusion["time_min"] / interval))
    high = min(diffusion["steps"] // diffusion["sample_interval"], math.floor(diffusion["time_max"] / interval + 1e-10))
    if high - low + 1 < 3:
        raise ValueError("The MSD fit window must contain at least three produced samples")
    return json.loads(json.dumps(base, allow_nan=False))


def model_text_for_data(model_text, data_name="input-state.data"):
    """Change only one plain read_data filename, leaving the force field untouched."""
    if (not isinstance(model_text, str) or len(model_text.encode("utf-8")) > 65536
            or not isinstance(data_name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*\.data", data_name)
            or data_name == STATE):
        raise ValueError("A stage needs a bounded model.in and a separate safe input data filename")
    lines = model_text.splitlines(keepends=True)
    found = []
    for index, line in enumerate(lines):
        words = line.split("#", 1)[0].split()
        if words and words[0] == "read_data":
            if len(words) != 2:
                raise ValueError("Only the generated PET model's plain read_data is supported")
            found.append(index)
    if len(found) != 1:
        raise ValueError("model.in must contain exactly one plain read_data")
    line = lines[found[0]]
    comment = " #" + line.split("#", 1)[1].rstrip("\r\n") if "#" in line else ""
    lines[found[0]] = f"read_data {data_name}{comment}\n"
    return "".join(lines)


def stage_parameters(recipe, stage, *, temperature=None, seed=None):
    """Existing LAMMPS case fields used by the new script; no execution options."""
    recipe = validate_recipe(recipe)
    if stage not in STAGES:
        raise ValueError("Unknown PET study stage")
    config = recipe[stage]
    if stage == "tg":
        if temperature not in config["temperatures"]:
            raise ValueError("Choose a temperature from the frozen cooling sequence")
    elif temperature is not None and temperature != config["temperature"]:
        raise ValueError("The stage temperature differs from its frozen recipe")
    values = {key: config[key] for key in ("pressure", "timestep", "steps", "equilibration_steps", "sample_interval")}
    values["temperature"] = temperature if stage == "tg" else config["temperature"]
    if stage == "relax":
        if seed is not None and seed != config["seed"]:
            raise ValueError("The velocity seed differs from the frozen recipe")
        values["seed"] = config["seed"]
    elif seed is not None:
        raise ValueError("Downstream stages retain state velocities; they do not redraw a seed")
    if stage == "modulus":
        values["strain_rate"] = config["strain_rate"]
    return values


def _oxygen_inputs(recipe, model_text, data_name, state_data_text):
    from .script import commands
    from .structure import parse_data
    if not isinstance(state_data_text, str):
        raise ValueError("O2 insertion requires the frozen pure-PET state data text")
    structure = parse_data(state_data_text)
    # The reader validates velocity widths, finite values and unique known IDs,
    # but also permits geometry-only data. O2 needs a saved dynamical handoff.
    velocity_ids, velocities = set(), False
    for line in state_data_text.splitlines():
        words = line.split("#", 1)[0].split()
        if not words:
            continue
        if words[0][0].isalpha():
            velocities = words == ["Velocities"]
        elif velocities:
            velocity_ids.add(int(words[0]))
    if velocity_ids != {atom.id for atom in structure.atoms}:
        raise ValueError("O2 insertion requires complete saved PET velocities for every atom")
    model = recipe["model"]
    chain_atoms = 22 * model["chain_length"] + 3
    molecules = Counter(atom.molecule for atom in structure.atoms)
    if (len(structure.atoms) != chain_atoms * model["chain_count"]
            or len(structure.bonds) != (23 * model["chain_length"] + 2) * model["chain_count"]
            or len(molecules) != model["chain_count"] or min(molecules) <= 0
            or set(molecules.values()) != {chain_atoms}):
        raise ValueError("The O2 insertion source must have the frozen pure-PET chain topology")
    charge = {identity: 0.0 for identity in molecules}
    for atom in structure.atoms:
        charge[atom.molecule] += atom.charge
    if any(abs(value) > 1e-6 for value in charge.values()):
        raise ValueError("O2 insertion requires neutral PET chains")
    atom_by_id = structure.atom_by_id
    if any(atom_by_id[bond.atoms[0]].molecule != atom_by_id[bond.atoms[1]].molecule
           for bond in structure.bonds):
        raise ValueError("The PET insertion source has a bond between chains")
    settings = {name: [words for _, words in commands(model_text) if words[0] == name]
                for name in ("pair_style", "pair_modify", "bond_style", "special_bonds")}
    if (settings["pair_style"] != [["pair_style", "lj/cut/coul/long", "12.0"]]
            or settings["pair_modify"] != [["pair_modify", "mix", "geometric"]]
            or settings["bond_style"] != [["bond_style", "harmonic"]]
            or settings["special_bonds"] != [["special_bonds", "lj/coul", "0.0", "0.0", "0.5"]]):
        raise ValueError("O2 protocol requires the archived PET 12-6 geometric OPLS settings")
    atom_types, bond_types = structure.counts.get("atom_types", 0), structure.counts.get("bond_types", 0)
    if min(atom_types, bond_types) < 1:
        raise ValueError("PET source lacks atom or bond types")
    rewritten = model_text_for_data(model_text, data_name)
    rewritten = re.sub(r"(?m)^read_data ([^\s#]+)",
                       r"read_data \1 extra/atom/types 1 extra/bond/types 1 extra/bond/per/atom 1 extra/special/per/atom 1",
                       rewritten, count=1)
    profile = oxygen_profile()
    config = recipe["diffusion"]
    metadata = {**profile, "PET_forcefield_profile": PROFILE_ID, "input_state_sha256": hashlib.sha256(state_data_text.encode()).hexdigest(),
                "gas_count": config["gas_count"], "gas_seed": config["gas_seed"],
                "overlap_distance_A": config["overlap_distance"], "insertion_attempts": config["insertion_attempts"],
                "atom_type": atom_types + 1, "bond_type": bond_types + 1,
                "expected_atoms": len(structure.atoms) + 2 * config["gas_count"],
                "expected_bonds": len(structure.bonds) + config["gas_count"],
                "molecule_id_lower_bound": max(molecules) + 1,
                "group": "gas", "MSD_scope": "O2 molecular COM, single origin, finite-time",
                "insertion": "random nonoverlap rejection; not GCMC or an equilibrium sorption calculation",
                "polymer_handoff": "retain source coordinates and velocities before MD; only remove whole-system linear momentum",
                "reproducibility": "orientation/IDs may depend on MPI rank count; freeze actual state and execution options"}
    half = profile["bond_length_A"] / 2
    molecule = (f"# {OXYGEN_PROFILE}; neutral two-site O2\n\n2 atoms\n1 bonds\n\nCoords\n\n"
                f"1 {-half:.17g} 0 0\n2 {half:.17g} 0 0\n\nTypes\n\n1 1\n2 1\n\n"
                "Charges\n\n1 0.0\n2 0.0\n\nBonds\n\n1 1 1 2\n")
    insertion = [f"mass {atom_types + 1} {profile['mass_g_mol']:.17g}",
                 f"pair_coeff {atom_types + 1} {atom_types + 1} {profile['LJ_epsilon_kcal_mol']:.17g} {profile['lammps_LJ_sigma_A']:.17g}",
                 f"bond_coeff {bond_types + 1} {profile['lammps_harmonic_K_kcal_mol_A2']:.17g} {profile['bond_length_A']:.17g}",
                 f"molecule oxygen oxygen.mol offset {atom_types} {bond_types} 0 0 0",
                 f"create_atoms 0 random {config['gas_count']} {config['gas_seed']} NULL mol oxygen {config['gas_seed']} overlap {config['overlap_distance']:.17g} maxtry {config['insertion_attempts']} units box",
                 f"group gas type {atom_types + 1}", f"group polymer type 1:{atom_types}",
                 "variable gas_atom_count equal count(gas)", *_gas_count_checks(config, metadata),
                 "# Preserve the saved PET thermal state: FIRE would reset every atom's velocity.",
                 f"velocity gas create ${{temperature}} {config['gas_seed']} mom no rot no dist gaussian",
                 "velocity all zero linear"]
    return rewritten, {"oxygen.mol": molecule, "gas-model.json": json.dumps(metadata, indent=2, allow_nan=False) + "\n"}, insertion, metadata


def _gas_count_checks(config, metadata):
    return [f'if "$(count(gas)) != {2 * config["gas_count"]}" then "print \'ERROR: O2 tracer atom count mismatch\'" "quit 1"',
            f'if "$(count(all)) != {metadata["expected_atoms"]}" then "print \'ERROR: PET/O2 total atom count mismatch\'" "quit 1"']


def exact_forcefield_files(original_data_text):
    """Restore coefficient types from the first frozen model, never a rounded state.

    The standard-library reader validates finite tables and bounded IDs. These
    commands retain the original writer's type numbering and real-unit values.
    They do not reconstruct parameters from coordinates, or change atom masses,
    charges, topology, velocity, box or PET profile 1.
    """
    from .structure import parse_data
    if not isinstance(original_data_text, str):
        raise ValueError("Downstream PET stages require the first frozen model data text")
    structure = parse_data(original_data_text)
    styles = {"Pair Coeffs": ("pair", "lj/cut/coul/long", 2), "Bond Coeffs": ("bond", "harmonic", 2),
              "Angle Coeffs": ("angle", "harmonic", 2), "Dihedral Coeffs": ("dihedral", "opls", 4),
              "Improper Coeffs": ("improper", "cvff", 3)}
    if structure.coefficients["PairIJ Coeffs"]:
        raise ValueError("PET exact restoration requires self LJ coefficients and geometric cross mixing")
    commands, tables, formats = [], {}, {}
    for section, (kind, style, width) in styles.items():
        entries = structure.coefficients[section]
        count = structure.counts.get(("atom" if kind == "pair" else kind) + "_types", 0)
        if set(entries) != set(range(1, count + 1)) or any(len(values) != width for values in entries.values()):
            raise ValueError("The first PET model has an incomplete or unsupported coefficient table")
        rows = []
        for identity, values in sorted(entries.items()):
            numbers = [format(value, ".17g") for value in values]
            if kind == "improper":
                if values[1] not in (-1., 1.) or not values[2].is_integer() or not 1 <= values[2] <= 6:
                    raise ValueError("CVFF sign and multiplicity must be supported explicit integers")
                numbers[1:] = [str(int(value)) for value in values[1:]]
            ids = f"{identity} {identity}" if kind == "pair" else str(identity)
            commands.append(f"{kind}_coeff {ids} " + " ".join(numbers))
            rows.append({"type": identity, "values": list(values)})
        tables[section] = rows
        directory = "KSPACE" if kind == "pair" else "MOLECULE"
        source_name = "pair_lj_cut_coul_long" if kind == "pair" else f"{kind}_{style}"
        formats[section] = {"style": style, "float_format": "%g (six significant digits)",
                            "integer_columns": [1, 2] if kind == "improper" else [],
                            "source": f"https://raw.githubusercontent.com/lammps/lammps/stable_22Jul2025/src/{directory}/{source_name}.cpp"}
    source_sha = hashlib.sha256(original_data_text.encode("utf-8")).hexdigest()
    text = f"# Exact PET coefficients from first frozen pet.data SHA256 {source_sha}\n" + "\n".join(commands) + "\n"
    metadata = {"format": "stk.pet-exact-forcefield/1", "PET_forcefield_profile": PROFILE_ID,
                "source_data_sha256": source_sha, "commands_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "tables": tables, "write_data_representation": formats,
                "reason": "restore original coefficients after reading LAMMPS text-state rounding; no cumulative drift"}
    return {"forcefield-exact.in": text, "forcefield-exact.json": json.dumps(metadata, indent=2, allow_nan=False) + "\n"}


def make_stage_files(recipe, stage, model_text, *, data_name="input-state.data", temperature=None, seed=None,
                     state_data_text=None, original_data_text=None):
    """Stage inputs as text. The caller copies/freeze-hashes data and ancestors.

    Tg stages use the previous temperature's state, while modulus/diffusion use
    their corresponding saved cooling state. O2 insertion draws only tracer velocities;
    the archived pure-PET input remains separate from the expanded final state.
    """
    recipe = validate_recipe(recipe)
    values = stage_parameters(recipe, stage, temperature=temperature, seed=seed)
    config = recipe[stage]
    extra_files, insertion, gas_metadata = {}, [], None
    new_model = model_text_for_data(model_text, data_name)
    if stage == "diffusion" and config["group"] == "o2_com":
        new_model, extra_files, insertion, gas_metadata = _oxygen_inputs(recipe, model_text, data_name, state_data_text)
    if stage != "relax":
        extra_files.update(exact_forcefield_files(original_data_text))
        # Restore after read_data has loaded its rounded coefficient tables,
        # before model.in completes and before any new O2 coefficients are set.
        lines = new_model.splitlines(keepends=True)
        index = next(index for index, line in enumerate(lines) if line.split("#", 1)[0].split()[:1] == ["read_data"])
        lines.insert(index + 1, "include forcefield-exact.in\n")
        new_model = "".join(lines)
    def num(value): return str(value) if type(value) is int else format(value, ".17g")
    script = [f"# {FORMAT}; {recipe['mode']}; finite protocol, material properties not validated",
              "# Force field remains the archived PET profile; output state.data is not proof of equilibrium.",
              "units real", "atom_style full", "boundary p p p"]
    script += [f"variable {key} index {num(value)}" for key, value in values.items()]
    script += ["include model.in", *insertion, "timestep ${timestep}", "thermo ${sample_interval}",
               "thermo_style custom step atoms temp press density pe ebond eangle edihed eimp evdwl ecoul elong" + (" v_gas_atom_count" if gas_metadata else ""),
               "thermo_modify format float %.15g"]
    if stage == "relax":
        compression = num(config["compression_pressure"])
        script += ["min_style fire", "minimize 1.0e-8 1.0e-8 5000 50000", "reset_timestep 0",
                   "velocity all create ${temperature} ${seed} mom yes rot yes dist gaussian",
                   "fix warm all nvt temp ${temperature} ${temperature} 100", f"run {config['warmup_steps']}", "unfix warm",
                   f"fix compact all npt temp ${{temperature}} ${{temperature}} 100 iso ${{pressure}} {compression} 1000",
                   f"run {config['compression_steps']}", "unfix compact",
                   f"fix release all npt temp ${{temperature}} ${{temperature}} 100 iso {compression} ${{pressure}} 1000",
                   "run ${equilibration_steps}", "unfix release"]
    elif stage == "tg":
        index = config["temperatures"].index(temperature)
        previous = recipe["relax"]["temperature"] if index == 0 else config["temperatures"][index - 1]
        script += [f"fix cool all npt temp {num(previous)} ${{temperature}} 100 iso ${{pressure}} ${{pressure}} 1000",
                   "run ${equilibration_steps}", "unfix cool"]
    else:
        script += ["fix relax all npt temp ${temperature} ${temperature} 100 iso ${pressure} ${pressure} 1000",
                   "run ${equilibration_steps}", "unfix relax"]
    script += ["reset_timestep 0", f"dump trajectory all custom {config['dump_interval']} {TRAJECTORY} id mol type q xu yu zu",
               "dump_modify trajectory sort id first yes", "dump_modify trajectory format float %.17g"]
    if stage == "modulus":
        script += ["variable initial_length equal $(lx:%.15g)", "variable strain_sample equal (lx-v_initial_length)/v_initial_length",
                   "variable stress_sample equal -pxx*0.000101325",
                   "fix ensemble all npt temp ${temperature} ${temperature} 100 y ${pressure} ${pressure} 1000 z ${pressure} ${pressure} 1000",
                   "fix stretch all deform 1 x erate ${strain_rate} remap x",
                   'fix samples all ave/time ${sample_interval} 1 ${sample_interval} v_strain_sample v_stress_sample file stress-strain.dat title1 "# PET engineering strain, tensile stress GPa; finite rate" title2 "Step Strain Stress"',
                   "thermo_style custom step temp press density pe v_strain_sample v_stress_sample"]
    elif stage == "diffusion":
        group, compute = ("gas", "gas_msd") if gas_metadata else ("all", "chain_msd")
        label = "O2 molecular COM tracer" if gas_metadata else "PET-chain COM"
        script += ["fix ensemble all nvt temp ${temperature} ${temperature} 100",
                   ("# O2 molecular COM MSD; finite tracer concentration, one origin; not permeability." if gas_metadata else
                    "# Whole PET-chain COM self MSD; one origin; not gas diffusion or permeability."),
                   f"compute molecules {group} chunk/atom molecule compress yes nchunk once ids once",
                   f"compute {compute} {group} msd/chunk molecules", f"variable mean_msd equal ave(c_{compute}[4])",
                   "variable elapsed equal time",
                   f'fix samples all ave/time ${{sample_interval}} 1 ${{sample_interval}} v_elapsed v_mean_msd file msd.dat title1 "# {label} MSD Angstrom^2; time fs; one origin; physical convergence unresolved" title2 "Step Time MSD"',
                   "thermo_style custom step atoms temp press density pe v_mean_msd" + (" v_gas_atom_count" if gas_metadata else "")]
    else:
        script += ["fix ensemble all npt temp ${temperature} ${temperature} 100 iso ${pressure} ${pressure} 1000"]
    script += ["run ${steps}"]
    if gas_metadata:
        script += _gas_count_checks(config, gas_metadata)
    if stage in {"modulus", "diffusion"}:
        script.append("unfix samples")
    if stage == "modulus":
        script.append("unfix stretch")
    script += ["unfix ensemble", "undump trajectory", f"write_data {STATE}"]
    return {"model.in": new_model, f"in.{stage}": "\n".join(script) + "\n", **extra_files}
