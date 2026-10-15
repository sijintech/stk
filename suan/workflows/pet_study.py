"""A persistent PET study composed of the existing workflow and analysis runs.

The ordinary parameter row is never updated by execution. A separate links row
records child identities and frozen handoff receipts, not lifecycle states. The
local ``pet-study/1`` template is explicitly started through workflow_runs; reads
and reopening never execute or contact a Runtime or model.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from suan.project import ProjectError
from suan.runtime.models import relative_path
from . import lammps, pet
from .common import (_canonical, _capture, _cells, _create_table, _directory,
                     _folder, _hash, _revision, _table)


FORMAT = "stk.pet-study/1"
TEMPLATE = "pet-study/1"
TABLE_ID = str(uuid5(NAMESPACE_URL, "urn:stk:pet-study:parameters:1"))
LINK_TABLE_ID = str(uuid5(NAMESPACE_URL, "urn:stk:pet-study:links:1"))
FIELDS = {"name": ("Study / 研究", "text", None),
          "recipe": ("Frozen protocol / 冻结协议", "json", None),
          "intent": ("Runtime intent / 运行环境意图", "json", None),
          "wait_seconds": ("Coordinator wait budget / 跟踪等待预算", "integer", "s")}
LINK_FIELDS = {"study": ("Study ID / 研究 ID", "text", None),
               "anchor": ("Workflow run ID / 工作流运行 ID", "text", None),
               "objects": ("Child IDs and receipts / 子运行与交接", "json", None)}
FIELD_IDS = {key: str(uuid5(UUID(TABLE_ID), key)) for key in FIELDS}
LINK_FIELD_IDS = {key: str(uuid5(UUID(LINK_TABLE_ID), key)) for key in LINK_FIELDS}
MAX_SECONDS = 24 * 60 * 60
MAX_WAIT_SECONDS = 31 * 24 * 60 * 60
POLL_SECONDS = 0.2


class StudyCancelled(ProjectError):
    """The explicitly started study was cancelled before its next action."""


def _id(study, name):
    return str(uuid5(UUID(study), "pet-study/1:" + name))


def _sha(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _check(cancel):
    if cancel is not None and cancel.is_set():
        raise StudyCancelled("PET study was cancelled")


def _revision_now(project):
    return project.snapshot()["project"]["revision"]


def _edit(project, operation):
    """Retry unrelated revision races; never silently retry another error."""
    from suan.scripting import ScriptError
    for _ in range(10):
        try:
            return operation(_revision_now(project))
        except ScriptError as error:
            if error.code != "conflict":
                raise
        time.sleep(0.02)
    raise ProjectError("The project kept changing while recording the PET study")


def _not_found(error):
    return getattr(error, "code", None) == "not_found"


def _maybe(get, identity):
    try:
        return get(identity)
    except Exception as error:
        if not _not_found(error):
            raise
        return None


def _workflow_document(table, template, *, metadata, parameters=None):
    return {"format": "stk.workflow/1", "ui": {}, "steps": [
        {"id": "cases", "kind": "table", "ref": {"table": table}},
        {"id": "execute", "kind": "simulation", "ref": {"template": template},
         "inputs": {"rows": {"from": "cases.rows"}},
         "parameters": parameters or {}, "x-pet-study": metadata},
    ]}


def _saved_workflow(project, identity, name, document):
    existing = _maybe(project.workflows.get, identity)
    if existing is not None:
        if existing["workflow"]["state"] != "readable" or existing["workflow"]["document"] != document:
            raise ProjectError("The PET child workflow changed; restore it before resuming")
        return identity
    _edit(project, lambda revision: project.workflows.create(
        name, document, workflow_id=identity, expected_revision=revision))
    return identity


def _frozen_files(project, produced):
    """Materialize only the recorded snapshot mappings, checking every byte."""
    if type(produced) is not dict or type(produced.get("files")) is not dict or not produced.get("snapshot_id"):
        raise ProjectError("The PET input stage has no frozen files")
    if not 1 <= len(produced["files"]) <= 100:
        raise ProjectError("The PET input stage exceeds the 100-file limit")
    output, total = {}, 0
    for name, record in produced["files"].items():
        name = relative_path(name)
        resolved = project.snapshots.resolve(produced["snapshot_id"], record)
        size = resolved["size"]
        total += size
        if total > lammps.MAX_INPUT_BYTES:
            raise ProjectError("The PET input stage exceeds the 256 MiB limit")
        with Path(resolved["path"]).open("rb") as stream:
            raw = stream.read(size + 1)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != resolved["sha256"]:
            raise ProjectError("A frozen PET input changed while being read")
        output[name] = raw
    return output


def _write_files(directory, files):
    """Resume verified remnants, but never replace caller-owned or altered bytes."""
    directory = Path(directory)
    for name, raw in files.items():
        name = relative_path(name)
        target = _folder(directory, *Path(name).parts[:-1]) / Path(name).name
        if target.is_symlink():
            raise ProjectError("PET study outputs must not be symbolic links")
        if target.exists():
            if not target.is_file() or _hash(target) != hashlib.sha256(raw).hexdigest():
                raise ProjectError("A PET study file changed; inspect it before resuming")
        else:
            with target.open("xb") as stream:
                stream.write(raw)
    return [directory / name for name in files]


def _coefficient_match(expected, actual, *, section, identity, changes):
    """Accept only full precision or the known LAMMPS write_data %g form.

    The five frozen PET styles serialize their coefficients with C's default
    six significant digits. This is a representation check, not a larger
    physical tolerance. Each changed value and the path that accepted it are
    retained in the state audit.
    """
    if len(expected) != len(actual):
        return False
    for component, (reference, value) in enumerate(zip(expected, actual)):
        if section == "Improper Coeffs" and component in (1, 2):
            # CVFF sign and multiplicity are written with %d, never %g.
            if value != reference:
                return False
            continue
        rounded = float(format(reference, ".6g"))
        close = lambda x, y: math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-15)
        if value == reference:
            continue
        if rounded != reference and value == rounded:
            path = "lammps_write_data_6g"
        elif close(value, reference):
            path = "numeric_tolerance"
        else:
            return False
        changes.append({"section": section, "type": identity, "component": component,
                        "reference": reference, "actual": value,
                        "six_significant_digits": rounded, "accepted_by": path})
    return True


def _validate_state(before_bytes, after_bytes, recipe, stage, *, forcefield_bytes=None):
    """Prove chemistry/parameters survive a state handoff; coordinates may evolve."""
    from collections import Counter
    from suan.lammps.structure import parse_data
    before = parse_data(before_bytes.decode("utf-8"))
    reference = before if forcefield_bytes is None else parse_data(forcefield_bytes.decode("utf-8"))
    after_text = after_bytes.decode("utf-8")
    after = parse_data(after_text)
    velocity_ids, velocities = set(), False
    for line in after_text.splitlines():
        words = line.split("#", 1)[0].split()
        if not words:
            continue
        if words[0][0].isalpha():
            velocities = words == ["Velocities"]
        elif velocities:
            velocity_ids.add(int(words[0]))  # the reader already validates these records
    if velocity_ids != set(after.atom_by_id):
        raise ProjectError("PET final state must preserve velocities for every atom")
    gas_count = recipe["diffusion"].get("gas_count", 0) if stage == "diffusion" and recipe["diffusion"]["group"] == "o2_com" else 0
    if len(after.atoms) != len(before.atoms) + 2 * gas_count:
        raise ProjectError("PET final state has an incorrect atom or tracer count")
    for kind in ("atom", "bond", "angle", "dihedral", "improper"):
        added = 1 if gas_count and kind in ("atom", "bond") else 0
        if before.counts.get(kind + "_types", 0) != reference.counts.get(kind + "_types", 0):
            raise ProjectError("PET input state force-field type counts differ from the first frozen model")
        if after.counts.get(kind + "_types", 0) != before.counts.get(kind + "_types", 0) + added:
            raise ProjectError("PET final state changed unexpected force-field type counts")
    by_id = after.atom_by_id
    for atom in before.atoms:
        current = by_id.get(atom.id)
        if (current is None or (current.molecule, current.type) != (atom.molecule, atom.type)
                or not math.isclose(current.charge, atom.charge, rel_tol=0, abs_tol=1e-10)):
            raise ProjectError("PET final state changed a polymer atom identity, molecule, type or charge")
    for kind in ("bonds", "angles", "dihedrals", "impropers"):
        previous = Counter((term.type, term.atoms) for term in getattr(before, kind))
        current = Counter((term.type, term.atoms) for term in getattr(after, kind))
        if not previous <= current or sum((current - previous).values()) != (gas_count if kind == "bonds" else 0):
            raise ProjectError("PET final state changed the polymer bonded topology")
    for identity, mass in before.masses.items():
        if identity not in after.masses or not math.isclose(mass, after.masses[identity], rel_tol=1e-9, abs_tol=1e-10):
            raise ProjectError("PET final state changed a polymer atom mass")
    input_changes, changes = [], []
    for section, terms in reference.coefficients.items():
        expected_keys = set(terms)
        if gas_count and section in ("Pair Coeffs", "Bond Coeffs"):
            kind = "atom" if section == "Pair Coeffs" else "bond"
            expected_keys.add(before.counts[kind + "_types"] + 1)
        if set(before.coefficients[section]) != set(terms) or set(after.coefficients[section]) != expected_keys:
            raise ProjectError("PET final state changed unexpected force-field coefficient records")
        for key, values in terms.items():
            if not _coefficient_match(values, before.coefficients[section][key], section=section,
                                      identity=key, changes=input_changes):
                raise ProjectError("PET input state changed polymer force-field coefficients")
            if not _coefficient_match(values, after.coefficients[section][key], section=section,
                                      identity=key, changes=changes):
                raise ProjectError("PET final state changed polymer force-field coefficients")
    if gas_count:
        from suan.lammps.pet_protocol import oxygen_profile
        profile = oxygen_profile()
        atoms = [atom for atom in after.atoms if atom.id not in before.atom_by_id]
        atom_type = before.counts["atom_types"] + 1
        molecules = Counter(atom.molecule for atom in atoms)
        first_molecule = max(atom.molecule for atom in before.atoms) + 1
        if (len(molecules) != gas_count or set(molecules.values()) != {2}
                or set(molecules) != set(range(first_molecule, first_molecule + gas_count))
                or any(atom.type != atom_type or atom.charge != 0.0 for atom in atoms)
                or not math.isclose(after.masses.get(atom_type, 0), 15.9994, rel_tol=0, abs_tol=1e-9)):
            raise ProjectError("O2 tracer molecule identities, masses or neutral charges are invalid")
        previous = Counter((term.type, term.atoms) for term in before.bonds)
        extra = Counter((term.type, term.atoms) for term in after.bonds) - previous
        bonded_atoms = Counter()
        for (bond_type, pair), multiplicity in extra.items():
            if (multiplicity != 1 or bond_type != before.counts.get("bond_types", 0) + 1
                    or any(identity not in {atom.id for atom in atoms} for identity in pair)
                    or by_id[pair[0]].molecule != by_id[pair[1]].molecule):
                raise ProjectError("O2 tracer bonds are inconsistent with the inserted molecules")
            bonded_atoms.update(pair)
        if bonded_atoms != Counter({atom.id: 1 for atom in atoms}):
            raise ProjectError("Every O2 tracer atom must have exactly one intramolecular bond")
        expected_pair = (profile["LJ_epsilon_kcal_mol"], profile["lammps_LJ_sigma_A"])
        expected_bond = (profile["lammps_harmonic_K_kcal_mol_A2"], profile["bond_length_A"])
        if (not _coefficient_match(expected_pair, after.coefficients["Pair Coeffs"].get(atom_type, ()),
                                   section="Pair Coeffs", identity=atom_type, changes=changes)
                or not _coefficient_match(expected_bond, after.coefficients["Bond Coeffs"].get(before.counts["bond_types"] + 1, ()),
                                          section="Bond Coeffs", identity=before.counts["bond_types"] + 1, changes=changes)):
            raise ProjectError("O2 tracer force-field coefficients differ from the frozen published profile")
    return {"atoms_before": len(before.atoms), "atoms_after": len(after.atoms), "added_o2_molecules": gas_count,
            "input_state_sha256": hashlib.sha256(before_bytes).hexdigest(),
            "output_state_sha256": hashlib.sha256(after_bytes).hexdigest(),
            "polymer_identity_and_forcefield": "preserved", "velocity_atom_count": len(velocity_ids),
            "coefficient_reference_sha256": hashlib.sha256(before_bytes if forcefield_bytes is None else forcefield_bytes).hexdigest(),
            "coefficient_representation": "full_precision_or_lammps_write_data_6g",
            "input_coefficient_rounding": input_changes, "coefficient_rounding": changes}


def _validate_exact_forcefield(original_bytes, scripts):
    """Independently bind the executable restoration to the first model data."""
    from suan.lammps.structure import parse_data
    original = parse_data(original_bytes.decode("utf-8"))
    kinds = {"Pair Coeffs": "pair", "Bond Coeffs": "bond", "Angle Coeffs": "angle",
             "Dihedral Coeffs": "dihedral", "Improper Coeffs": "improper"}
    if original.coefficients["PairIJ Coeffs"]:
        raise ProjectError("PET exact restoration requires the original self LJ coefficient tables")
    expected, tables = [], {}
    for section, kind in kinds.items():
        rows = []
        for identity, values in sorted(original.coefficients[section].items()):
            expected.append((kind + "_coeff", (identity, identity) if kind == "pair" else (identity,), values))
            rows.append({"type": identity, "values": list(values)})
        tables[section] = rows
    try:
        commands = scripts["forcefield-exact.in"]
        parsed = []
        for line in commands.splitlines():
            words = line.split("#", 1)[0].split()
            if not words:
                continue
            if words[0] == "improper_coeff":
                # LAMMPS inumeric rejects floating-point tokens even when
                # their numerical values happen to be integral.
                if any(str(int(value)) != value for value in words[3:5]):
                    raise ValueError("CVFF commands require canonical integer tokens")
            ids = 2 if words[0] == "pair_coeff" else 1
            parsed.append((words[0], tuple(int(value) for value in words[1:ids + 1]),
                           tuple(float(value) for value in words[ids + 1:])))
        metadata = json.loads(scripts["forcefield-exact.json"])
        model_commands = [words for line in scripts["model.in"].splitlines()
                          if (words := line.split("#", 1)[0].split())]
        read_indices = [i for i, words in enumerate(model_commands) if words[0] == "read_data"]
        includes = [words for words in model_commands if words[0] == "include"]
        source_sha = hashlib.sha256(original_bytes).hexdigest()
        commands_sha = hashlib.sha256(commands.encode("utf-8")).hexdigest()
        valid = (parsed == expected and metadata["format"] == "stk.pet-exact-forcefield/1"
                 and metadata["PET_forcefield_profile"] == "stk.pet.opls-mk2022/1"
                 and metadata["source_data_sha256"] == source_sha and metadata["commands_sha256"] == commands_sha
                 and _canonical(metadata["tables"]) == _canonical(tables)
                 and len(read_indices) == 1 and includes == [["include", "forcefield-exact.in"]]
                 and model_commands[read_indices[0] + 1] == ["include", "forcefield-exact.in"])
    except (KeyError, ValueError, TypeError, IndexError):
        valid = False
    if not valid:
        raise ProjectError("PET downstream exact coefficient restoration differs from the first frozen model")
    return {"original_forcefield_data_sha256": source_sha, "exact_coefficients_sha256": commands_sha}


def _series_csv(logs):
    from suan.lammps.analysis import density_series
    table = density_series(logs)
    return "Temperature,Density,Source,Samples\n" + "".join(
        f"{float(t):.17g},{float(d):.17g},{name},{int(n)}\n" for t, d, name, n in
        zip(*(table.column(name) for name in ("Temperature", "Density", "Source", "Samples"))))


def _analysis_document(kind, recipe, source):
    from suan.graph.catalog import load_preset
    graph = load_preset("lammps-" + kind)
    values = recipe[kind]
    if kind == "tg":
        graph["nodes"][0] = {"id": "data", "type": "stk.source.lammps_density_series@1", "params": {
            "binding": "data", "paths": [name for name in source["files"] if name.startswith("logs/")],
            "receipt_path": "tg-series.json"}}
        graph["parameters"] = [parameter for parameter in graph["parameters"] if parameter["name"] != "path"]
        parameters = {}
    elif kind == "modulus":
        parameters = {"path": "case/stress-strain.dat", "strain_min": values["strain_min"], "strain_max": values["strain_max"]}
    else:
        parameters = {"path": "case/msd.dat", "time_min": values["time_min"], "time_max": values["time_max"], "dimensions": values["dimensions"]}
    # Preserve valid observations when a scientifically rejected fit produces
    # no fit output, so the ordinary graph service can archive its errors.
    graph["outputs"]["observations"] = "data.out"
    return {"format": "stk.analysis-document/1", "graph": graph, "parameters": parameters,
            "outputs": ["observations", "summary", "fit", "diagnostics", "plot"]}


def _validate_analysis_run(run, project_id, definition, document, source):
    selected = {binding: {name: value["record_id"] for name, value in files.items()}
                for binding, files in run["bindings"].items()}
    if (run["project_id"] != project_id or run["analysis_id"] != definition
            or run["document"] != document or run["snapshot_id"] != source["snapshot_id"]
            or selected != {"data": source["files"]} or run.get("parameter_overrides")):
        raise ProjectError("A PET analysis belongs to a different study, frozen definition, fit window or full source bindings")


class PetStudy:
    def __init__(self, stk):
        self.stk = stk

    def _project(self, project=None, expected_revision=None):
        project = project or self.stk.project
        model = project.snapshot() if expected_revision is None else _revision(project, expected_revision)
        if model["format_version"] not in (13, 14):
            raise ProjectError("PET studies require project format 13 or 14; upgrade explicitly first")
        return project, model

    def _record(self, project, study_id):
        UUID(study_id)
        model = project.snapshot()
        table = _table(model, TABLE_ID, FIELDS, FIELD_IDS, "PET study")
        row = next((row for row in table["records"] if row["id"] == study_id), None) if table else None
        if row is None or any(value.get("state") != "ok" for value in row.get("evaluations", {}).values()):
            raise ProjectError("Select a PET study row without expression errors")
        return model, row

    def _links(self, project, study_id, anchor):
        model = project.snapshot()
        table = _table(model, LINK_TABLE_ID, LINK_FIELDS, LINK_FIELD_IDS, "PET study links")
        row = next((row for row in table["records"] if row["id"] == _id(study_id, "links")), None) if table else None
        if row is None:
            return {}
        values = row["values"]
        if (any(value.get("state") != "ok" for value in row.get("evaluations", {}).values())
                or values.get(LINK_FIELD_IDS["study"]) != study_id
                or values.get(LINK_FIELD_IDS["anchor"]) != anchor
                or type(values.get(LINK_FIELD_IDS["objects"])) is not dict):
            raise ProjectError("The PET study links row has changed or is invalid")
        return deepcopy(values[LINK_FIELD_IDS["objects"]])

    def _save(self, project, study_id, anchor, objects):
        def apply(revision):
            model = _revision(project, revision)
            table = _table(model, LINK_TABLE_ID, LINK_FIELDS, LINK_FIELD_IDS, "PET study links")
            commands = [] if table else _create_table(LINK_TABLE_ID, "PET study links / PET 研究关联", LINK_FIELDS, LINK_FIELD_IDS)
            record = _id(study_id, "links")
            if table is None or not any(row["id"] == record for row in table["records"]):
                commands.append({"op": "add_record", "table_id": LINK_TABLE_ID, "id": record})
            commands += _cells(LINK_TABLE_ID, record, {"study": study_id, "anchor": anchor, "objects": objects}, LINK_FIELD_IDS)
            return project.apply(commands, expected_revision=revision)
        return _edit(project, apply)

    def create(self, recipe=None, *, connection, expected_revision, options=None, name="PET study / PET 研究",
               project=None, study_id=None, wait_seconds=None):
        """Freeze a study and its Runtime intent. No modeling, upload or submission."""
        from suan.lammps.pet_protocol import validate_recipe
        from suan.lammps.spec import lammps_spec
        from suan.project.managed import name as valid_name
        from suan.runtime.models import TaskSpec
        recipe = validate_recipe({} if recipe is None else recipe)
        wait_seconds = (MAX_WAIT_SECONDS if recipe["mode"] == "research" else MAX_SECONDS) if wait_seconds is None else wait_seconds
        if type(wait_seconds) is not int or not 1 <= wait_seconds <= MAX_WAIT_SECONDS:
            raise ProjectError("PET study wait_seconds must be an integer between 1 and 2678400")
        name = valid_name(name, "PET study")
        if type(connection) is not str or connection.startswith("hub:"):
            raise ProjectError("PET studies require a saved direct or SSH Runtime connection")
        options = deepcopy({} if options is None else options)
        if type(options) is not dict or set(options) & {"workspace_id", "case_dir", "inputs", "name"}:
            raise ProjectError("PET study resource options cannot replace owned inputs or task names")
        TaskSpec(**lammps_spec("0" * 32, case_dir="case", name="PET study", **options))
        if (recipe["diffusion"]["group"] == "o2_com"
                and recipe["diffusion"]["gas_seed"] + options.get("ranks", 1) - 1 > 900000000):
            raise ProjectError("O2 gas_seed plus MPI rank offsets exceeds the LAMMPS RanMars range")
        project, model = self._project(project, expected_revision)
        study_id = str(uuid4()) if study_id is None else str(UUID(study_id))
        intent = {"connection": connection, "options": options}
        workflow, anchor = _id(study_id, "workflow"), _id(study_id, "anchor")
        table = _table(model, TABLE_ID, FIELDS, FIELD_IDS, "PET study")
        row = next((row for row in table["records"] if row["id"] == study_id), None) if table else None
        if row is not None:
            if (row["values"].get(FIELD_IDS["recipe"]) != recipe or row["values"].get(FIELD_IDS["intent"]) != intent
                    or row["values"].get(FIELD_IDS["wait_seconds"]) != wait_seconds):
                raise ProjectError("This PET study identity belongs to a different recipe or Runtime intent")
            if _maybe(project.workflow_runs.get, anchor) is not None:
                existing = self.get(study_id, project=project)
                if existing["simulation"]["connection"] != connection or existing["simulation"]["options"] != options:
                    raise ProjectError("This PET study identity belongs to a different Runtime intent")
                return existing
            # An interrupted create may have saved the definition before its
            # immutable run. Complete it explicitly, under the caller's revision.
        else:
            commands = [] if table else _create_table(TABLE_ID, "PET studies / PET 研究", FIELDS, FIELD_IDS)
            commands.append({"op": "add_record", "table_id": TABLE_ID, "id": study_id})
            commands += _cells(TABLE_ID, study_id, {"name": name, "recipe": recipe, "intent": intent,
                                                   "wait_seconds": wait_seconds}, FIELD_IDS)
            project.apply(commands, expected_revision=expected_revision)
        document = _workflow_document(TABLE_ID, TEMPLATE,
            metadata={"format": FORMAT, "study_id": study_id, "recipe_sha256": _sha(recipe),
                      "runtime_intent_sha256": _sha(intent), "wait_seconds": wait_seconds},
            parameters={"recipe": {"$field": FIELD_IDS["recipe"]}, "study_id": study_id,
                        "wait_seconds": {"$field": FIELD_IDS["wait_seconds"]}})
        _saved_workflow(project, workflow, name, document)
        project.workflow_runs.prepare(workflow, [study_id], run_id=anchor,
            expected_revision=_revision_now(project), connection=connection, options=options)
        self._save(project, study_id, anchor, {})
        return self.get(study_id, project=project)

    def get(self, study_id, *, project=None):
        """Read pinned plans and journals only; never refresh Runtime tasks."""
        project, _ = self._project(project)
        model, row = self._record(project, study_id)
        anchor = _id(study_id, "anchor")
        run = _maybe(project.workflow_runs.get, anchor)
        if run is None:
            return {"study_id": study_id, "table_id": TABLE_ID, "project_id": model["project"]["id"],
                    "revision": model["project"]["revision"], "recipe": row["values"].get(FIELD_IDS["recipe"]),
                    "simulation": row["values"].get(FIELD_IDS["intent"]), "workflow_id": _id(study_id, "workflow"),
                    "run_id": None, "status": "incomplete", "complete": False, "tasks": [], "stages": {},
                    "objects": {}, "definition_changed": False,
                    "wait_seconds": row["values"].get(FIELD_IDS["wait_seconds"]),
                    "error": "Creation stopped before freezing the anchor; explicitly recover or repeat create with the same study ID."}
        if (run["project_id"] != model["project"]["id"] or run["table_id"] != TABLE_ID
                or run["workflow_id"] != _id(study_id, "workflow") or len(run["rows"]) != 1
                or run["rows"][0]["id"] != study_id or run["order"] != ["execute"]
                or run["steps"].get("execute", {}).get("template") != TEMPLATE
                or run["parameters"].get("execute", {}).get(study_id, {}).get("study_id") != study_id):
            raise ProjectError("The PET study anchor belongs to a different project or template")
        recipe = run["parameters"]["execute"][study_id]["recipe"]
        wait_seconds = run["parameters"]["execute"][study_id]["wait_seconds"]
        simulation = run.get("simulation")
        if type(simulation) is not dict or set(simulation) != {"connection", "connection_identity", "options"}:
            raise ProjectError("The PET study has no frozen Runtime intent")
        intent = {key: simulation[key] for key in ("connection", "options")}
        meta = run["document"]["steps"][1].get("x-pet-study")
        if meta != {"format": FORMAT, "study_id": study_id, "recipe_sha256": _sha(recipe),
                    "runtime_intent_sha256": _sha(intent), "wait_seconds": wait_seconds}:
            raise ProjectError("The PET study frozen recipe metadata is inconsistent")
        objects = self._links(project, study_id, anchor)
        allowed = {"model", "relax", "tg_inputs", "property:modulus", "property:diffusion",
                   *(f"property:tg:{index}" for index in range(len(recipe["tg"]["temperatures"]))),
                   *("analysis:" + kind for kind in ("tg", "modulus", "diffusion"))}
        if set(objects) - allowed:
            raise ProjectError("The PET study links contain an unknown stage")
        stages = {}
        for key, item in objects.items():
            if key in ("model", "relax") or key.startswith("property:"):
                record = _id(study_id, "model:row") if key == "model" else _id(study_id, key + ":case")
                if (type(item) is not dict or set(item) != {"workflow_id", "run_id", "record_id"}
                        or item != {"workflow_id": _id(study_id, key + ":workflow"),
                                    "run_id": _id(study_id, key + ":run"), "record_id": record}):
                    raise ProjectError("A PET child identity belongs to a different study")
                child = project.workflow_runs.get(item["run_id"])
                template = "pet-model/1" if key == "model" else "lammps/1"
                metadata = {"format": FORMAT, "study_id": study_id, "stage": key, "recipe_sha256": _sha(recipe)}
                if (child["project_id"] != run["project_id"] or child["workflow_id"] != item["workflow_id"]
                        or len(child["rows"]) != 1 or child["rows"][0]["id"] != record
                        or child["steps"].get("execute", {}).get("template") != template
                        or child["document"]["steps"][1].get("x-pet-study") != metadata
                        or (key != "model" and child.get("simulation") != simulation)):
                    raise ProjectError("A PET child run belongs to a different study")
                stages[key] = {"run_id": child["id"], "status": child["status"], "complete": child["complete"],
                               "counts": child["counts"], "tasks": child["tasks"]}
            elif key.startswith("analysis:"):
                if (type(item) is not dict or set(item) != {"analysis_id", "run_id", "snapshot_id", "previous_run_ids"}
                        or item["analysis_id"] != _id(study_id, key + ":definition")
                        or type(item["previous_run_ids"]) is not list):
                    raise ProjectError("The PET analysis identities are invalid")
                child = project.analysis_runs.get(item["run_id"])
                if key == "analysis:tg":
                    expected_source = objects.get("tg_inputs")
                else:
                    property_item = objects.get("property:" + key.split(":", 1)[1])
                    property_run = project.workflow_runs.get(property_item["run_id"]) if property_item else None
                    expected_source = (property_run["tasks"][0].get("produced")
                                       if property_run and property_run["complete"] else None)
                if child["snapshot_id"] != item["snapshot_id"] or not expected_source:
                    raise ProjectError("A PET analysis belongs to a different study")
                kind = key.split(":", 1)[1]
                _validate_analysis_run(child, run["project_id"], item["analysis_id"],
                                       _analysis_document(kind, recipe, expected_source), expected_source)
                stages[key] = {"run_id": child["id"], "status": child["status"], "error": child["error"], "result": child["result"]}
            elif key == "tg_inputs":
                if type(item) is not dict or set(item) != {"snapshot_id", "files"}:
                    raise ProjectError("The PET density series snapshot mapping is invalid")
                # A read checks membership without reading files or executing a
                # source. Actual frozen bytes are reverified on execution.
                snapshot = project.snapshots.get(item["snapshot_id"])
                ids = {entry["record_id"] for entry in snapshot["manifest"]["files"]}
                if type(item["files"]) is not dict or not set(item["files"].values()) <= ids:
                    raise ProjectError("The PET density-series files do not belong to its snapshot")
        if "tg_inputs" in objects:
            self._verify_tg_inputs(project, study_id, recipe, objects)
        return {"study_id": study_id, "table_id": TABLE_ID, "project_id": run["project_id"],
                "revision": model["project"]["revision"], "recipe": recipe, "simulation": run.get("simulation"),
                "workflow_id": run["workflow_id"], "run_id": anchor, "status": run["status"],
                "complete": run["complete"], "tasks": run["tasks"], "stages": stages, "objects": objects,
                "wait_seconds": wait_seconds,
                "definition_changed": (row["values"].get(FIELD_IDS["recipe"]) != recipe
                                       or row["values"].get(FIELD_IDS["intent"]) != intent
                                       or row["values"].get(FIELD_IDS["wait_seconds"]) != wait_seconds)}

    status = get

    def start(self, study_id, *, expected_revision, project=None):
        project, _ = self._project(project, expected_revision)
        result = self.get(study_id, project=project)
        if result["run_id"] is None:
            raise ProjectError("Complete PET study creation explicitly before starting it")
        if result["definition_changed"]:
            raise ProjectError("The PET recipe changed; create a new study instead of changing the frozen one")
        if not result["complete"]:
            project.workflow_runs.start(result["run_id"])
        return self.get(study_id, project=project)

    def advance(self, study_id, *, expected_revision, submit=False, project=None):
        """Inspection without submit; an explicit submit starts/resumes the anchor."""
        if type(submit) is not bool:
            raise ProjectError("submit must be a boolean")
        project, _ = self._project(project, expected_revision)
        return self.start(study_id, expected_revision=expected_revision, project=project) if submit else self.get(study_id, project=project)

    def cancel(self, study_id, *, expected_revision, project=None):
        project, _ = self._project(project, expected_revision)
        result = self.get(study_id, project=project)
        if result["run_id"] is None:
            return result  # no execution exists to cancel
        project.workflow_runs.cancel(result["run_id"])
        self._cancel_children(project, result["objects"])
        return self.get(study_id, project=project)

    def recover(self, study_id, *, expected_revision, project=None, force=False):
        """Explicit recovery only; it does not start or replay any computation."""
        if type(force) is not bool:
            raise ProjectError("force must be a boolean")
        project, _ = self._project(project, expected_revision)
        result = self.get(study_id, project=project)
        if result["run_id"] is None:
            _, row = self._record(project, study_id)
            intent = row["values"].get(FIELD_IDS["intent"])
            if type(intent) is not dict or set(intent) != {"connection", "options"}:
                raise ProjectError("The incomplete PET study Runtime intent changed")
            return self.create(result["recipe"], connection=intent["connection"], options=intent["options"],
                               name=row["values"][FIELD_IDS["name"]], expected_revision=expected_revision,
                               project=project, study_id=study_id, wait_seconds=result["wait_seconds"])
        project.workflow_runs.recover(result["run_id"], force=force)
        for key, item in result["objects"].items():
            if key in ("model", "relax") or key.startswith("property:"):
                project.workflow_runs.recover(item["run_id"], force=force)
            elif key.startswith("analysis:"):
                project.analysis_runs.recover(item["run_id"])
        return self.get(study_id, project=project)

    def _model_definition(self, project, study_id, recipe):
        table_id, row_id = _id(study_id, "model:table"), _id(study_id, "model:row")
        fields = {key: _id(study_id, "model:field:" + key) for key in pet.FIELDS}
        model = project.snapshot()
        table = _table(model, table_id, pet.FIELDS, fields, "PET model")
        if table is None:
            commands = _create_table(table_id, "PET model parameters / PET 建模参数", pet.FIELDS, fields)
            commands.append({"op": "add_record", "table_id": table_id, "id": row_id})
            commands += _cells(table_id, row_id, recipe["model"], fields)
            _edit(project, lambda revision: project.apply(commands, expected_revision=revision))
        else:
            row = next((row for row in table["records"] if row["id"] == row_id), None)
            if row is None or any(row["values"].get(fields[key]) != recipe["model"][key] for key in fields):
                raise ProjectError("The PET model parameter row changed after the study was frozen")
        return table_id, row_id, {key: {"$field": value} for key, value in fields.items()}

    def _case(self, project, study_id, key, files, parameters):
        record = _id(study_id, key + ":case")
        scripts = [name for name in files if name.startswith("in.")]
        if len(scripts) != 1:
            raise ProjectError("A PET stage must declare exactly one generated main script")
        script = scripts[0]
        checked = lammps.check_script(files[script].decode("utf-8"), list(files),
                                       lambda name: files[name].decode("utf-8"))
        model = project.snapshot()
        table = lammps._case_table(model)
        row = next((row for row in table["records"] if row["id"] == record), None) if table else None
        if row is not None:
            values = lammps._case_values(table, row)
            frozen = _frozen_files(project, {"snapshot_id": values["source"]["snapshot_id"],
                                           "files": values["source"]["bindings"]})
            if (frozen != files or values.get("script") != script or values.get("attempt") != 1
                    or values["source"].get("parameters") != checked["used"]
                    or any(values.get(name) != parameters.get(name) for name in lammps.PARAMETERS)):
                raise ProjectError("The PET derived case changed; create a new study instead")
            return record, deepcopy(values)
        directory = _folder(_directory(self.stk, project), "inputs", "pet-studies", study_id, key.replace(":", "-"))
        paths = _write_files(directory, files)
        indexed, captured = _capture(project, paths, [_hash(path) for path in paths], _revision_now(project))
        source = {"snapshot_id": captured["snapshot"]["id"], "bindings": dict(zip(files, indexed["record_ids"])),
                  "parameters": checked["used"]}
        values = {"name": "PET " + key, "script": script,
                  **{name: parameters.get(name) for name in lammps.PARAMETERS}, "attempt": 1, "source": source}
        commands = lammps._extend_case_fields(lammps._case_table(project.snapshot()))
        commands.append({"op": "add_record", "table_id": lammps.TABLE_ID, "id": record})
        commands += _cells(lammps.TABLE_ID, record, values, lammps.FIELD_IDS)
        _edit(project, lambda revision: project.apply(commands, expected_revision=revision))
        return record, deepcopy(values)

    def _child(self, project, study_id, key, table, row, template, parameters, recipe, target, objects, cancel, deadline,
               approved_values=None):
        document = _workflow_document(table, template, parameters=parameters,
            metadata={"format": FORMAT, "study_id": study_id, "stage": key, "recipe_sha256": _sha(recipe)})
        workflow, run_id = _id(study_id, key + ":workflow"), _id(study_id, key + ":run")
        _saved_workflow(project, workflow, "PET " + key, document)
        existing = _maybe(project.workflow_runs.get, run_id)
        if existing is None:
            _check(cancel)
            kwargs = {"connection": target["connection"], "options": target["options"]} if template == "lammps/1" else {}
            existing = _edit(project, lambda revision: project.workflow_runs.prepare(
                workflow, [row], run_id=run_id, expected_revision=revision, **kwargs))
        if (existing["document"] != document or existing["table_id"] != table or existing["order"] != ["execute"]
                or len(existing["rows"]) != 1 or existing["rows"][0]["id"] != row
                or (template == "lammps/1" and existing.get("simulation") != target)):
            raise ProjectError("PET child inputs or Runtime endpoint identity differ from the frozen study")
        # Completed runs skip the core executor's live-row comparison. Bind
        # them here too: a separately prepared off-protocol child must not be
        # adopted merely because somebody restored its editable row afterwards.
        if template == "lammps/1":
            if approved_values is None:
                raise ProjectError("A PET remote child needs its previously approved frozen case values")
            expected_values = approved_values
        else:
            expected_values = recipe["model"]
        if _canonical(existing["parameters"].get("execute", {}).get(row)) != _canonical(expected_values):
            raise ProjectError("The PET child frozen parameters or source differ from the approved stage")
        item = {"workflow_id": workflow, "run_id": run_id, "record_id": row}
        if objects.get(key) != item:
            objects[key] = item
            self._save(project, study_id, _id(study_id, "anchor"), objects)
        if not existing["complete"]:
            _check(cancel)
            if existing["status"] not in ("running", "cancel_requested"):
                project.workflow_runs.start(run_id)
            while True:
                _check(cancel)
                existing = project.workflow_runs.get(run_id)
                if existing["complete"]:
                    break
                if existing["status"] not in ("running", "cancel_requested"):
                    failure = next((task.get("error") for task in existing["tasks"] if task.get("error")), None)
                    raise ProjectError("PET " + key + " did not finish: " + (failure or {}).get("message", "inspect its workflow run"))
                if time.monotonic() > deadline:
                    raise ProjectError("PET study exceeded its orchestration time budget")
                cancel.wait(POLL_SECONDS)
        tasks = existing["tasks"]
        if len(tasks) != 1 or tasks[0]["status"] != "succeeded":
            raise ProjectError("The PET child workflow must have one successful task")
        return tasks[0]["produced"]

    def _stage(self, project, study_id, key, stage, recipe, original, source, target, objects, cancel, deadline, temperature=None):
        from suan.lammps.pet_protocol import make_stage_files, stage_parameters
        raw = _frozen_files(project, source)
        state_name = "pet.data" if stage == "relax" else "case/state.data"
        if state_name not in raw:
            raise ProjectError("The PET upstream stage did not freeze its declared final state")
        scripts = make_stage_files(recipe, stage, original["model.in"].decode("utf-8"),
                                   data_name="input-state.data", temperature=temperature,
                                   original_data_text=original["pet.data"].decode("utf-8"),
                                   **({"state_data_text": raw[state_name].decode("utf-8")}
                                      if stage == "diffusion" and recipe["diffusion"]["group"] == "o2_com" else {}))
        restored = _validate_exact_forcefield(original["pet.data"], scripts) if stage != "relax" else {}
        files = {"input-state.data": raw[state_name], **{name: text.encode("utf-8") for name, text in scripts.items()},
                 "source/pet-model.json": original["pet-model.json"], "source/forcefield.xml": original["forcefield.xml"],
                 "source/original-model.in": original["model.in"]}
        receipt = {"format": "stk.pet-stage/1", "study_id": study_id, "stage": key, "recipe_sha256": _sha(recipe),
                   "source_snapshot_id": source["snapshot_id"], "source_files": source["files"],
                   "input_state_sha256": hashlib.sha256(raw[state_name]).hexdigest(),
                   "files": {name: hashlib.sha256(value).hexdigest() for name, value in files.items()},
                   "limits": "Frozen handoff is not evidence of equilibration or a converged material property."}
        files["pet-stage.json"] = (_canonical(receipt) + "\n").encode("utf-8")
        parameters = stage_parameters(recipe, stage, temperature=temperature)
        record, approved_values = self._case(project, study_id, key, files, parameters)
        produced = self._child(project, study_id, key, lammps.TABLE_ID, record, "lammps/1", {},
                               recipe, target, objects, cancel, deadline, approved_values=approved_values)
        final = _frozen_files(project, produced)
        if "case/state.data" not in final:
            raise ProjectError("The PET solver did not freeze its declared final state")
        audit = _validate_state(raw[state_name], final["case/state.data"], recipe, stage,
                                forcefield_bytes=original["pet.data"])
        audit.update(restored)
        return {**produced, "state_validation": audit}

    def _tg_inputs(self, project, study_id, recipe, points):
        files, logs, entries = {}, {}, []
        for index, source in enumerate(points):
            raw = _frozen_files(project, source)
            path = f"logs/tg-{index:03d}.log"
            text = raw["case/log.lammps"]
            files[path] = text
            logs[path] = text.decode("utf-8")
            entries.append({"path": path, "sha256": hashlib.sha256(text).hexdigest(),
                            "simulation_run_id": source["simulation_run_id"], "snapshot_id": source["snapshot_id"],
                            "record_id": source["files"]["case/log.lammps"], "temperature_set_K": recipe["tg"]["temperatures"][index]})
        csv = _series_csv(logs)
        receipt = {"format": "stk.pet-density-series/1", "study_id": study_id, "recipe_sha256": _sha(recipe),
                   "logs": entries, "averaging": "last thermo block, second half",
                   "temperature_path_K": recipe["tg"]["temperatures"],
                   "density_csv_sha256": hashlib.sha256(csv.encode("utf-8")).hexdigest(),
                   "limits": "Finite cooling history; inspect equilibration and independent configurations."}
        files["density-temperature.csv"] = csv.encode("utf-8")
        files["tg-series.json"] = (_canonical(receipt) + "\n").encode("utf-8")
        directory = _folder(_directory(self.stk, project), "results", "pet-studies", study_id, "density-series")
        paths = _write_files(directory, files)
        indexed, captured = _capture(project, paths, [_hash(path) for path in paths], _revision_now(project))
        return {"snapshot_id": captured["snapshot"]["id"], "files": dict(zip(files, indexed["record_ids"]))}

    def _verify_tg_inputs(self, project, study_id, recipe, objects):
        """Bind aggregation bytes to this study's exact completed temperature runs."""
        from suan.graph.nodes.pet_study_sources import _receipt
        source = objects["tg_inputs"]
        names = [f"logs/tg-{index:03d}.log" for index in range(len(recipe["tg"]["temperatures"]))]
        if set(source["files"]) != {*names, "tg-series.json", "density-temperature.csv"}:
            raise ProjectError("The PET density series has missing or unexpected members")
        snapshot = project.snapshots.get(source["snapshot_id"])
        files = {entry["record_id"]: entry for entry in snapshot["manifest"]["files"]}
        raw = _frozen_files(project, {"snapshot_id": source["snapshot_id"],
                                     "files": {"tg-series.json": source["files"]["tg-series.json"]}})
        receipt = _receipt(raw["tg-series.json"])
        entries, logs, total = [], {}, 0
        for index, (path, temperature) in enumerate(zip(names, recipe["tg"]["temperatures"])):
            item = objects.get(f"property:tg:{index}")
            if item is None:
                raise ProjectError("The PET density series has no matching temperature workflow")
            run = project.workflow_runs.get(item["run_id"])
            if not run["complete"] or len(run["tasks"]) != 1 or not run["tasks"][0].get("produced"):
                raise ProjectError("The PET density series refers to an unfinished temperature run")
            original = run["tasks"][0]["produced"]
            original_snapshot = project.snapshots.get(original["snapshot_id"])
            record = original["files"]["case/log.lammps"]
            entry = next(entry for entry in original_snapshot["manifest"]["files"] if entry["record_id"] == record)
            digest = entry["sha256"]
            if files[source["files"][path]]["sha256"] != digest:
                raise ProjectError("The PET density series log differs from its own frozen temperature run")
            total += entry["size"]
            if total > lammps.MAX_INPUT_BYTES:
                raise ProjectError("The PET density-series original logs exceed 256 MiB")
            original_log = _frozen_files(project, {"snapshot_id": original["snapshot_id"],
                                                  "files": {path: record}})[path]
            logs[path] = original_log.decode("utf-8")
            entries.append({"path": path, "sha256": digest, "simulation_run_id": original["simulation_run_id"],
                            "snapshot_id": original["snapshot_id"], "record_id": record, "temperature_set_K": temperature})
        if (receipt.get("format") != "stk.pet-density-series/1" or receipt.get("study_id") != study_id
                or receipt.get("recipe_sha256") != _sha(recipe)
                or _canonical(receipt.get("logs")) != _canonical(entries)
                or receipt.get("temperature_path_K") != recipe["tg"]["temperatures"]
                or receipt.get("density_csv_sha256") != files[source["files"]["density-temperature.csv"]]["sha256"]
                or receipt.get("density_csv_sha256") != hashlib.sha256(_series_csv(logs).encode("utf-8")).hexdigest()):
            raise ProjectError("The PET density series receipt belongs to a different study or cooling history")

    def _analysis(self, project, study_id, kind, recipe, source, objects, attempt, submit=True):
        document = _analysis_document(kind, recipe, source)
        key = "analysis:" + kind
        definition = _id(study_id, key + ":definition")
        project_id = project.snapshot()["project"]["id"]

        def validate_run(run):
            _validate_analysis_run(run, project_id, definition, document, source)

        existing = _maybe(project.analyses.get, definition)
        if existing is None:
            _edit(project, lambda revision: project.analyses.create("PET " + kind, document,
                analysis_id=definition, expected_revision=revision))
        elif existing["analysis"]["document"] != document:
            raise ProjectError("The PET saved analysis changed; restore it before resuming")
        prior = objects.get(key)
        if prior:
            run = project.analysis_runs.get(prior["run_id"])
            validate_run(run)
            if run["status"] == "succeeded":
                project.analysis_runs.result(run["id"])
                return run
        run_id = _id(study_id, key + f":attempt:{attempt}")
        run = _maybe(project.analysis_runs.get, run_id)
        if run is None:
            run = _edit(project, lambda revision: project.analysis_runs.prepare(definition, source["snapshot_id"],
                {"data": source["files"]}, run_id=run_id, expected_revision=revision))
        validate_run(run)
        history = list((prior or {}).get("previous_run_ids", []))
        if prior and prior["run_id"] != run_id and prior["run_id"] not in history:
            history.append(prior["run_id"])
        objects[key] = {"analysis_id": definition, "run_id": run_id, "snapshot_id": source["snapshot_id"],
                        "previous_run_ids": history}
        self._save(project, study_id, _id(study_id, "anchor"), objects)
        return project.analysis_runs.start(run_id) if submit and run["status"] == "prepared" else run

    def analyze(self, study_id, *, expected_revision, submit=False, project=None):
        """Prepare/start missing analyses of already frozen successful stages."""
        if type(submit) is not bool:
            raise ProjectError("submit must be a boolean")
        project, _ = self._project(project, expected_revision)
        status = self.get(study_id, project=project)
        objects, recipe = status["objects"], status["recipe"]
        if not all(key in objects for key in ("tg_inputs", "property:modulus", "property:diffusion")):
            raise ProjectError("Complete and freeze PET property sampling before analyzing it")
        if status["status"] in ("running", "cancel_requested"):
            raise ProjectError("The PET study already has an active executor")
        attempt = max((task["attempt"] for task in status["tasks"]), default=0) + 1
        self._verify_tg_inputs(project, study_id, recipe, objects)
        for kind in ("tg", "modulus", "diffusion"):
            source = objects["tg_inputs"] if kind == "tg" else project.workflow_runs.get(
                objects["property:" + kind]["run_id"])["tasks"][0]["produced"]
            self._analysis(project, study_id, kind, recipe, source, objects, attempt, submit=submit)
        return self.get(study_id, project=project)

    @staticmethod
    def _cancel_children(project, objects):
        for key, item in objects.items():
            if key in ("model", "relax") or key.startswith("property:"):
                run = project.workflow_runs.get(item["run_id"])
                if run["status"] in ("running", "cancel_requested"):
                    project.workflow_runs.cancel(run["id"])
            elif key.startswith("analysis:"):
                run = project.analysis_runs.get(item["run_id"])
                if run["status"] in ("prepared", "running"):
                    project.analysis_runs.cancel(run["id"])


def execute_local(*, stk, cleanup_stk, parameters, directory, cancel, context):
    """Run inside the canonical workflow executor, which owns cancel/recovery.

    This function has no independent task or lifecycle state. Every child is
    prepared and recorded before starting. A retry reuses successful children;
    a failed/unknown single-attempt analysis gets a new run under the new outer
    attempt. Scientifically rejected fits retain their failed archived results.
    """
    from suan.lammps.pet_protocol import validate_recipe
    study_id, recipe = parameters["study_id"], validate_recipe(parameters["recipe"])
    service, project = PetStudy(stk), stk.project
    status = service.get(study_id, project=project)
    if (context["run_id"] != status["run_id"] or context["row_id"] != study_id
            or recipe != status["recipe"] or context.get("simulation") != status["simulation"]):
        raise ProjectError("The PET coordinator does not match its frozen project study")
    target = context["simulation"]
    if type(target) is not dict or set(target) != {"connection", "connection_identity", "options"}:
        raise ProjectError("The PET study must freeze a Runtime intent before it starts")
    objects = status["objects"]
    deadline = time.monotonic() + parameters["wait_seconds"]
    completed = False
    try:
        _check(cancel)
        table, row, model_parameters = service._model_definition(project, study_id, recipe)
        model_source = service._child(project, study_id, "model", table, row, "pet-model/1", model_parameters,
                                      recipe, target, objects, cancel, deadline)
        original = _frozen_files(project, model_source)
        if set(original) != set(pet.OUTPUTS):
            raise ProjectError("PET modeling must freeze exactly the eight declared artifacts")
        with TemporaryDirectory(prefix="stk-pet-study-model-") as temporary:
            folder = Path(temporary)
            _write_files(folder, original)
            pet._outputs(folder, recipe["model"])
        _check(cancel)
        checks = {}
        state = service._stage(project, study_id, "relax", "relax", recipe, original, model_source,
                               target, objects, cancel, deadline)
        checks["relax"] = state["state_validation"]
        points, states = [], {}
        for index, temperature in enumerate(recipe["tg"]["temperatures"]):
            state = service._stage(project, study_id, f"property:tg:{index}", "tg", recipe, original, state,
                                   target, objects, cancel, deadline, temperature=temperature)
            points.append(state)
            states[temperature] = state
            checks[f"tg:{index}"] = state["state_validation"]
        if "tg_inputs" not in objects:
            objects["tg_inputs"] = service._tg_inputs(project, study_id, recipe, points)
            service._save(project, study_id, status["run_id"], objects)
        else:
            # Never silently regenerate a missing/corrupt aggregation snapshot.
            _frozen_files(project, objects["tg_inputs"])
        service._verify_tg_inputs(project, study_id, recipe, objects)
        for kind in ("modulus", "diffusion"):
            temperature = recipe[kind]["temperature"]
            sampled = service._stage(project, study_id, "property:" + kind, kind, recipe, original, states[temperature],
                                     target, objects, cancel, deadline, temperature=temperature)
            checks[kind] = sampled["state_validation"]
        sources = {"tg": objects["tg_inputs"]}
        for kind in ("modulus", "diffusion"):
            sources[kind] = project.workflow_runs.get(objects["property:" + kind]["run_id"])["tasks"][0]["produced"]
        for kind, source in sources.items():
            _check(cancel)
            service._analysis(project, study_id, kind, recipe, source, objects, context["attempt"])
        analyses = {}
        while len(analyses) != 3:
            _check(cancel)
            for kind in sources:
                run = project.analysis_runs.get(objects["analysis:" + kind]["run_id"])
                if run["status"] in ("succeeded", "failed", "cancelled", "unknown"):
                    if run["result"] is None:
                        raise ProjectError("PET " + kind + " analysis has no archived result: " + run["status"])
                    # Reading verifies every archived manifest and blob.
                    archived = project.analysis_runs.result(run["id"])
                    analyses[kind] = {"run_id": run["id"], "status": run["status"], "error": run["error"],
                                      "result": run["result"], "graph_errors": archived["result"].get("errors", [])}
            if time.monotonic() > deadline:
                raise ProjectError("PET study exceeded its analysis time budget")
            if len(analyses) != 3:
                cancel.wait(POLL_SECONDS)
        _check(cancel)
        output = {"format": FORMAT, "study_id": study_id, "anchor_run_id": status["run_id"],
                  "recipe": recipe, "recipe_sha256": _sha(recipe), "wait_seconds": parameters["wait_seconds"],
                  "objects": objects, "analyses": analyses,
                  "state_validation": checks,
                  "software_complete": True, "fits_resolved": all(value["status"] == "succeeded" for value in analyses.values()),
                  "material_validation": False,
                  "diffusion_scope": "O2 tracer COM" if recipe["diffusion"]["group"] == "o2_com" else "pure PET chain COM",
                  "limits": ["Short-chain finite-time MD is not converged PET material validation.",
                             "A rejected fit remains a failed analysis, with its archived diagnostic.",
                             ("O2 tracer MSD does not establish permeability, solubility or converged bulk gas diffusion."
                              if recipe["diffusion"]["group"] == "o2_com" else
                              "Pure PET chain-center MSD is not gas diffusion or barrier performance.")]}
        directory = Path(directory)
        directory.mkdir(exist_ok=False)
        _write_files(directory, {"pet-study.json": (_canonical(output) + "\n").encode("utf-8")})
        completed = True
    finally:
        if not completed:
            # Cancellation-aware APIs may refuse calls after cancellation. The
            # executor supplies a cleanup facade pinned to this same project.
            try:
                outer = cleanup_stk.project.workflow_runs.get(context["run_id"])
            except Exception as error:
                if not _not_found(error):
                    raise
            else:
                if outer["status"] == "cancel_requested":
                    PetStudy(cleanup_stk)._cancel_children(cleanup_stk.project, objects)


__all__ = ["PetStudy", "StudyCancelled", "execute_local", "FORMAT", "TEMPLATE", "TABLE_ID", "FIELD_IDS"]
