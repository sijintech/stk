"""Project-backed LAMMPS workflow (docs/design/multiscale-engines.md, E1), as the MuFerro one:
import -> edit the row -> prepare -> ProjectRuns.submit (or a workflow run) -> collect.

A case is a folder with one input script and the files it reads (data files, potentials, included scripts).
The row sets the parameters the script takes as variables (temperature, pressure, steps, timestep, seed;
suan/lammps/script.py); the others stay empty. A content-derived preparation identity reuses the same plan
after repeated clicks or a lost response; increment Attempt to run again.
"""
import hashlib
import json
from pathlib import Path
import shutil
import stat
from tempfile import TemporaryDirectory
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from suan.lammps.log import VERIFIER, verify_log
from suan.lammps.run import INPUT, INPUT_FORMAT, LOG, RESULT
from suan.lammps.script import OWN_FILES, PARAMETERS, PROPERTY_PARAMETERS, ScriptError, check_parameters, check_script
from suan.lammps.spec import lammps_spec
from suan.runtime.models import TaskSpec, relative_path
from .common import (_canonical, _capture, _cells, _copy_input, _create_table, _directory, _folder, _hash,
                     _revision, _table)


def identity(name):
    return str(uuid5(NAMESPACE_URL, "urn:stk:workflow:lammps:1:" + name))


TABLE_ID = identity("cases")
FIELDS = {
    "name": ("Case / 案例", "text", None),
    "script": ("Input script / 输入脚本", "text", None),
    "temperature": ("Temperature / 温度", "number", None),
    "pressure": ("Pressure / 压力", "number", None),
    "steps": ("Steps / 步数", "integer", None),
    "timestep": ("Time step / 时间步长", "number", None),
    "seed": ("Random seed / 随机种子", "integer", None),
    "attempt": ("Attempt / 尝试次数", "integer", None),
    "source": ("Frozen source / 原始输入版本", "json", None),
}
FIELDS.update({
    "equilibration_steps": ("Equilibration steps / 平衡步数", "integer", None),
    "sample_interval": ("Sample interval / 采样间隔", "integer", None),
    "strain_rate": ("Strain rate (1/fs) / 应变率", "number", None),
    "solute_type": ("Solute atom type / 溶质原子类型", "integer", None),
})
FIELD_IDS = {key: identity("case:" + key) for key in FIELDS}
RESULT_TABLE_ID = identity("results")
RESULT_FIELDS = {
    "run": ("Run ID", "text", None), "task": ("Task ID", "text", None),
    "temperature": ("Temperature (set)", "number", None), "pressure": ("Pressure (set)", "number", None),
    "units": ("LAMMPS units", "text", None), "step": ("Final step", "integer", None),
    "density": ("Density (mean)", "number", None), "temperature_mean": ("Temperature (mean)", "number", None),
    "pressure_mean": ("Pressure (mean)", "number", None), "potential_energy": ("Potential energy (mean)", "number", None),
    "thermo": ("Thermo summary", "json", None), "program": ("LAMMPS SHA-256", "text", None),
    "files": ("Result files", "json", None),
}
RESULT_FIELD_IDS = {key: identity("result:" + key) for key in RESULT_FIELDS}
LABEL = "LAMMPS / "
NAME = "LAMMPS"
MAX_INPUT_BYTES = 256 * 1024 * 1024
MAX_FILES = 100
SCRIPT_NAMES = ("in.*", "*.in", "*.lmp", "*.lammps")


def _case_table(model):
    """New property fields are optional on an E1a table; reads never migrate it."""
    table = next((t for t in model["tables"] if t["id"] == TABLE_ID), None)
    present = {f["id"] for f in table["fields"]} if table else set()
    required = {key: value for key, value in FIELDS.items()
                if key not in PROPERTY_PARAMETERS or FIELD_IDS[key] in present}
    return _table(model, TABLE_ID, required, FIELD_IDS, NAME)


def _extend_case_fields(table):
    if table is None:
        return _create_table(TABLE_ID, "LAMMPS cases / 分子动力学算例", FIELDS, FIELD_IDS)
    present = {f["id"] for f in table["fields"]}
    return [{"op": "add_field", "id": FIELD_IDS[key], "table_id": TABLE_ID, "name": FIELDS[key][0],
             "type": FIELDS[key][1]} for key in PROPERTY_PARAMETERS if FIELD_IDS[key] not in present]


def _case_values(table, row):
    present = {f["id"] for f in table["fields"]}
    return {key: row["values"].get(field) for key, field in FIELD_IDS.items() if field in present}


def _inputs(folder):
    """A clean case folder: regular files only, at most 100 files and 256 MiB, no LAMMPS outputs of STK's own."""
    folder = Path(folder).expanduser().resolve(strict=True)
    paths, pending, size, visited = [], [folder], 0, 0
    while pending:
        for path in sorted(pending.pop().iterdir()):
            visited += 1
            if visited > 256:
                raise ValueError("Use a clean case folder with at most 100 files and 256 entries")
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise ValueError("Case files must be regular files, without symbolic links")
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
            elif stat.S_ISREG(info.st_mode):
                if path.name in OWN_FILES:
                    raise ValueError(f"The case folder holds {path.name}; import a clean case without run outputs")
                paths.append(path)
                size += info.st_size
            else:
                raise ValueError("Case files must be regular files")
            if len(paths) > MAX_FILES or size > MAX_INPUT_BYTES:
                raise ValueError("Case exceeds 100 files or the 256 MiB input limit")
    if not paths:
        raise ValueError("The case folder is empty")
    return folder, sorted(paths)


def _script_name(names, script):
    if script is not None:
        script = relative_path(script)
        if script not in names:
            raise ValueError(f"The case has no file {script}")
        return script
    found = [name for name in names if "/" not in name and any(Path(name).match(p) for p in SCRIPT_NAMES)]
    if len(found) != 1:
        raise ValueError("Name the input script: the case has " + (", ".join(found[:5]) if found else "no in.* file"))
    return found[0]


def _check(folder, script):
    """Check the script and the scripts it includes; returns check_script's result."""
    names = [p.relative_to(folder).as_posix() for p in sorted(folder.rglob("*")) if p.is_file()]
    try:
        return check_script((folder / script).read_text(encoding="utf-8"), names,
                            lambda name: (folder / name).read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raise ValueError("Input scripts must be UTF-8 text") from None


def _source(source):
    """The frozen source of a case: its snapshot, file bindings and the parameters its script takes."""
    if not isinstance(source, dict) or set(source) != {"snapshot_id", "bindings", "parameters"} or \
            not isinstance(source["parameters"], list) or not set(source["parameters"]) <= set(PARAMETERS):
        raise ValueError("The case must reference its imported source snapshot, bindings and script parameters")
    return source


def _restore(project, source, folder):
    _source(source)
    bindings = source["bindings"]
    if not isinstance(bindings, dict) or not 1 <= len(bindings) <= MAX_FILES:
        raise ValueError("Invalid LAMMPS input bindings")
    for name, record_id in bindings.items():
        name = relative_path(name)
        if Path(name).name in OWN_FILES:
            raise ValueError("Invalid LAMMPS input filename")
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        resolved = project.snapshots.resolve(source["snapshot_id"], record_id)
        with path.open("xb") as out, Path(resolved["path"]).open("rb") as inp:
            shutil.copyfileobj(inp, out)


def _parameters(values):
    if type(values.get("attempt")) is not int or values["attempt"] < 1:
        raise ValueError("attempt must be a positive integer")
    if not isinstance(values.get("script"), str) or not values["script"]:
        raise ValueError("The row must name its input script")
    check_parameters(values, _source(values.get("source"))["parameters"])


TRAJECTORY_SUFFIXES = {".dump", ".lammpstrj", ".dcd", ".xtc", ".trr", ".nc", ".h5", ".xyz"}


def final_state(names):
    """What a downstream analysis needs from a collected run: the launcher report, the log, the case inputs and
    the files the run wrote, except trajectories (``*.dump``, ``*.lammpstrj``, ... or names with 'dump'), which stay
    in the results folder only. Never truncated: more than 100 files makes the workflow step fail visibly."""
    chosen = [RESULT] if RESULT in names else []
    for name in names:
        file = Path(name).name.lower()
        if name.startswith("case/") and Path(file).suffix not in TRAJECTORY_SUFFIXES and "dump" not in file:
            chosen.append(name)
    return chosen


def describe_case(model, record_id, connection, options, identity=None):
    """Validated row values, the task template and the plan label (as MuFerro's describe_case)."""
    table = _case_table(model)
    row = next((r for r in table["records"] if r["id"] == record_id), None) if table else None
    if row is None or any(e.get("state") != "ok" for e in row.get("evaluations", {}).values()):
        raise ValueError("Select a LAMMPS case row without formula errors")
    values = _case_values(table, row)
    _parameters(values)
    if connection.startswith("hub:"):
        raise ValueError("LAMMPS preparation uses direct/SSH Runtime profiles; Hub preparation is not supported")
    if set(options) & {"workspace_id", "case_dir", "inputs", "name"}:
        raise ValueError("The LAMMPS workflow owns workspace, input and task names")
    template = lammps_spec("0" * 32, case_dir="case", name=NAME, **options)
    TaskSpec(**template)
    if identity is not None and (type(identity) is not str or not 1 <= len(identity) <= 256):
        raise ValueError("A preparation identity is a short string")
    basis = {"project": model["project"]["id"], "record": record_id,
             "values": row["values"], "definitions": row.get("definitions", {}),
             "fields": {f["id"]: [f["type"], f.get("unit")] for f in table["fields"]},
             "connection": connection, "spec": template}
    if identity is not None:
        basis["identity"] = identity
    fingerprint = hashlib.sha256(_canonical(basis).encode("utf-8")).hexdigest()
    shown = f" · {values['temperature']:g}" if type(values.get("temperature")) in (int, float) else ""
    label = LABEL + str(values["name"])[:40] + shown + " / " + fingerprint
    return values, template, label


class Lammps:
    def __init__(self, stk):
        self.stk = stk

    def import_case(self, source, *, expected_revision, script=None, project=None):
        """Copy and freeze a clean case folder; create one editable case row, without execution.
        ``script`` names the input script when the folder has more than one ``in.*`` file."""
        p = project or self.stk.project
        model = _revision(p, expected_revision)
        table = _case_table(model)
        source, paths = _inputs(source)
        row_id = str(uuid4())
        root = _directory(self.stk, p)
        destination = _folder(root, "inputs", "lammps", row_id)
        copied, remaining = [], MAX_INPUT_BYTES
        for path in paths:
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            remaining -= _copy_input(path, target, remaining)
            copied.append(target)
        hashes = [_hash(path) for path in copied]
        names = [path.relative_to(destination).as_posix() for path in copied]
        try:
            name = _script_name(names, script)
            checked = _check(destination, name)  # what was copied, not the mutable original
        except (ScriptError, ValueError):
            shutil.rmtree(destination, ignore_errors=True)
            raise
        values = {"name": source.name, "script": name, **{key: checked["parameters"].get(key) for key in PARAMETERS},
                  "attempt": 1}
        indexed, captured = _capture(p, copied, hashes, expected_revision)
        values["source"] = {"snapshot_id": captured["snapshot"]["id"], "bindings": dict(zip(names, indexed["record_ids"])),
                            "parameters": checked["used"]}
        commands = _extend_case_fields(table)
        commands += [{"op": "add_record", "id": row_id, "table_id": TABLE_ID}]
        commands += _cells(TABLE_ID, row_id, values, FIELD_IDS)
        result = p.apply(commands, expected_revision=captured["revision"])
        unset = [key for key in checked["used"] if checked["parameters"].get(key) is None]
        print("Imported LAMMPS case:", row_id, "— parameters:", ", ".join(checked["used"]) or "none",
              *(["— set in the row:", ", ".join(unset)] if unset else []), flush=True)
        return {"table_id": TABLE_ID, "record_id": row_id, "revision": result["revision"],
                "parameters": checked["used"], "units": checked["units"]}

    def clone_case(self, record_id, *, expected_revision, project=None):
        """Copy evaluated parameters as literals, sharing the immutable imported source (parameters may still be empty)."""
        p = project or self.stk.project
        model = _revision(p, expected_revision)
        table = _case_table(model)
        row = next((r for r in table["records"] if r["id"] == record_id), None) if table else None
        if row is None or any(e.get("state") != "ok" for e in row.get("evaluations", {}).values()):
            raise ValueError("Select a LAMMPS case row without formula errors")
        values = _case_values(table, row)
        _source(values["source"])
        row_id = str(uuid4())
        commands = _extend_case_fields(table) + [{"op": "add_record", "id": row_id, "table_id": TABLE_ID}]
        commands += _cells(TABLE_ID, row_id, values, FIELD_IDS)
        result = p.apply(commands, expected_revision=expected_revision)
        print("Copied LAMMPS parameters:", row_id, flush=True)
        return {"record_id": row_id, "revision": result["revision"]}

    def prepare(self, record_id, connection, *, expected_revision, project=None, identity=None, **options):
        """Freeze inputs and prepare one plan; repeating the same row/options reuses it. Options are lammps_spec
        resource options (ranks, threads_per_rank, backend, program, launcher, walltime_seconds, ...)."""
        p = project or self.stk.project
        model = _revision(p, expected_revision)
        values, template, label = describe_case(model, record_id, connection, options, identity)
        fingerprint = label.rsplit(" / ", 1)[1]
        offset = 0
        while True:
            page = p.runs.list(offset=offset)
            for summary in page["runs"]:
                if summary["label"] == label:
                    run = p.runs.get(summary["id"])
                    if run["parameter_state"] != "current":
                        raise ValueError("Existing plan no longer matches these parameters; increment Attempt to prepare again")
                    p.runs.refresh(run["id"])
                    print("Reusing prepared LAMMPS run:", run["id"], flush=True)
                    return run
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        root = _directory(self.stk, p)
        with TemporaryDirectory(prefix="stk-lammps-") as scratch:
            folder = Path(scratch)
            _restore(p, values["source"], folder)
            if not (folder / relative_path(values["script"])).is_file():
                raise ValueError(f"The case has no file {values['script']}")
            checked = _check(folder, relative_path(values["script"]))
            variables = check_parameters(values, checked["used"])
            document = {"format": INPUT_FORMAT, "script": relative_path(values["script"]), "variables": variables}
            (folder / INPUT).write_text(json.dumps(document, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
            destination = _folder(root, "inputs", "lammps-prepared", fingerprint)
            paths, hashes = [], []
            for source in sorted(folder.rglob("*")):
                if not source.is_file():
                    continue
                target = destination / source.relative_to(folder)
                _folder(destination, *source.relative_to(folder).parts[:-1])
                if target.exists():
                    if target.is_symlink() or _hash(target) != _hash(source):
                        raise ValueError("Prepared input changed locally; inspect it before retrying")
                else:
                    with target.open("xb") as out, source.open("rb") as inp:
                        shutil.copyfileobj(inp, out)
                paths.append(target)
                hashes.append(_hash(source))
        indexed, captured = _capture(p, paths, hashes, expected_revision)
        snapshot_id = captured["snapshot"]["id"]
        bindings = dict(zip(["case/" + path.relative_to(destination).as_posix() for path in paths], indexed["record_ids"]))
        runtime = self.stk.runtime(connection)
        key = "lammps:" + fingerprint
        workspace = runtime.workspaces.create("LAMMPS " + fingerprint[:12], idempotency_key=key + ":workspace")["workspace"]["id"]
        for remote, file_id in bindings.items():
            source = p.snapshots.resolve(snapshot_id, file_id)["path"]
            transfer = runtime.upload(workspace, source, remote=remote,
                                      idempotency_key=key + ":input:" + hashlib.sha256(remote.encode()).hexdigest())
            self._transfer(transfer)
        spec = {**template, "workspace_id": workspace, "outputs": [RESULT, *bindings]}
        prepared = p.runs.prepare([{"table_id": TABLE_ID, "record_id": record_id, "label": label,
            "input_snapshot_id": snapshot_id, "input_bindings": bindings, "spec": spec}],
            connection=connection, expected_revision=captured["revision"])
        run = p.runs.get(prepared["run_ids"][0])
        print("Prepared LAMMPS run:", run["id"], "— no task submitted; inspect and submit in Runs", flush=True)
        return run

    def _transfer(self, transfer):
        result = self.stk.transfers.wait(transfer["id"], timeout=300)
        if result["state"] != "completed":
            raise RuntimeError(f"Transfer {result['id']} is {result['state']}; inspect Transfers and explicitly resume if needed")

    def _download(self, runtime, task, run_id, name, path, artifact):
        if path.is_symlink():
            raise ValueError("Result paths must not be symbolic links")
        if not path.exists():
            transfer = runtime.download(name, task_id=task["id"], dest=path,
                idempotency_key=f"lammps:{run_id}:result:" + hashlib.sha256(name.encode()).hexdigest())
            self._transfer(transfer)
        if not path.is_file() or path.stat().st_size != artifact["size"] or _hash(path) != artifact["sha256"]:
            raise ValueError(f"Result changed locally or was not downloaded: {name}; inspect Transfers before repairing")

    def collect(self, run_id, *, project=None, max_bytes=1024**3):
        """Download and verify one successful run, then register a stable result row. Never submits."""
        p = project or self.stk.project
        run = p.runs.refresh(run_id)
        plan, status = run["plan"], run["status"]
        if not plan["label"].startswith(LABEL) or plan["parameters"]["table_id"] != TABLE_ID:
            raise ValueError("Select a run prepared by the LAMMPS project workflow")
        task = status.get("task")
        if not task or task["state"] != "succeeded":
            raise ValueError("Collect requires a successfully finished task; inspect its state and logs")
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError("Invalid download budget")
        root = _directory(self.stk, p)
        destination = _folder(root, "results", "lammps", str(UUID(run_id)))
        runtime = self.stk.runtime(plan["connection"])
        artifacts = {item["path"]: item for item in runtime.tasks.artifacts(task["id"])}
        if RESULT not in artifacts or "case/" + LOG not in artifacts or any(name not in artifacts for name in plan["input_bindings"]):
            raise ValueError("Successful task has missing LAMMPS outputs or original inputs")
        if any(artifacts[f["path"]]["sha256"] != f["sha256"] for f in plan["inputs"]):
            raise ValueError("Task input bytes do not match the frozen run plan")
        if artifacts[RESULT]["size"] > 2 * 1024 * 1024:
            raise ValueError("The LAMMPS run report exceeds 2 MiB")
        self._download(runtime, task, run_id, RESULT, destination / RESULT, artifacts[RESULT])
        report = json.loads((destination / RESULT).read_text(encoding="utf-8"))
        outputs = report.get("outputs") if isinstance(report.get("outputs"), list) else []
        listed = {item.get("path"): item.get("sha256") for item in outputs if isinstance(item, dict)}
        if any(not isinstance(name, str) or name not in artifacts or artifacts[name]["sha256"] != digest
               for name, digest in listed.items()):
            raise ValueError("The run report lists outputs the Runtime does not have with the same content")
        names = sorted(set(plan["input_bindings"]) | {RESULT, "case/" + LOG} | set(listed))
        if len(names) > 10000 or sum(artifacts[name]["size"] for name in names) > max_bytes:
            raise ValueError("LAMMPS results exceed the download budget")
        paths = []
        for name in names:
            path = destination / relative_path(name)
            _folder(destination, *Path(name).parts[:-1])
            self._download(runtime, task, run_id, name, path, artifacts[name])
            paths.append(path)
        frozen = json.loads((destination / "case" / INPUT).read_text(encoding="utf-8"))
        verification = verify_log((destination / "case" / LOG).read_text(encoding="utf-8", errors="replace"))
        if (report.get("app") != "LAMMPS" or report.get("state") != "succeeded" or report.get("case_dir") != "case"
                or report.get("verification", {}).get("verifier") != VERIFIER
                or report.get("verification", {}).get("status") != "passed"
                or verification["verification"]["status"] != "passed" or verification["qoi"] != report.get("qoi")
                or report.get("script") != frozen["script"] or report.get("variables") != frozen["variables"]):
            raise ValueError("Collected LAMMPS output does not match its input/log contract")
        revision = p.snapshot()["project"]["revision"]
        for offset in range(0, len(paths), 100):
            revision = p.files.index(paths[offset:offset + 100], expected_revision=revision)["revision"]
        model = _revision(p, revision)
        table = _table(model, RESULT_TABLE_ID, RESULT_FIELDS, RESULT_FIELD_IDS, NAME)
        commands = [] if table else _create_table(RESULT_TABLE_ID, "LAMMPS results / 分子动力学结果", RESULT_FIELDS, RESULT_FIELD_IDS)
        row_id = str(uuid5(UUID(run_id), "lammps-result"))
        if table is None or not any(r["id"] == row_id for r in table["records"]):
            commands.append({"op": "add_record", "id": row_id, "table_id": RESULT_TABLE_ID})
        qoi = verification["qoi"]
        parameters = plan["parameters"]["values"]
        values = {"run": run_id, "task": task["id"], "temperature": parameters.get(FIELD_IDS["temperature"]),
                  "pressure": parameters.get(FIELD_IDS["pressure"]), "units": verification["units"], "step": qoi["step"],
                  "density": qoi["density"], "temperature_mean": qoi["temperature"], "pressure_mean": qoi["pressure"],
                  "potential_energy": qoi["potential_energy"],
                  "thermo": {"columns": qoi["columns"], "means": qoi["means"], "final": qoi["final"],
                             "samples": qoi["samples"], "runs": qoi["runs"], "version": verification["version"]},
                  "program": report.get("program", {}).get("sha256"),
                  "files": [{"path": path.relative_to(root).as_posix(), "sha256": artifacts[name]["sha256"]}
                            for name, path in zip(names, paths)]}
        commands += _cells(RESULT_TABLE_ID, row_id, values, RESULT_FIELD_IDS)
        p.apply(commands, expected_revision=revision)
        print("Collected LAMMPS run:", run_id, *(["— mean density:", qoi["density"]] if qoi["density"] is not None else []),
              flush=True)
        return {"run_id": run_id, "table_id": RESULT_TABLE_ID, "record_id": row_id,
                "directory": str(destination / "case"), "qoi": qoi, "files": values["files"]}
