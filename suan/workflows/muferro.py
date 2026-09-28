"""Project-backed muFerro workflow, shared by native controls and desktop Python.

No automatic submission: import -> edit -> prepare -> ProjectRuns.submit -> collect -> view.
The editable case row refers to frozen source files. A content-derived preparation identity
reuses the same plan after repeated clicks or a lost response; increment Attempt to run again.
All project changes use the public revisioned facade, never a second SQLite connection.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import os
import shutil
import stat
from tempfile import TemporaryDirectory
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from suan.connectors.mupro.inputs import dump_toml
from suan.mupro.run import (_toml_document, read_case, check_case, verify_run, expected_frames,
                            RUN_OUTPUTS, VERIFIER, tomllib)
from suan.mupro.spec import muferro_spec
from suan.runtime.models import TaskSpec, relative_path


def identity(name):
    return str(uuid5(NAMESPACE_URL, "urn:stk:workflow:muferro:1:" + name))


TABLE_ID = identity("cases")
FIELDS = {
    "name": ("Case / 案例", "text", None),
    "temperature": ("Temperature / 温度", "number", "K"),
    "steps": ("Steps / 步数", "integer", None),
    "dt": ("Time step / 时间步长", "number", None),
    "interval": ("Output interval / 输出间隔", "integer", None),
    "attempt": ("Attempt / 尝试次数", "integer", None),
    "source": ("Frozen source / 原始输入版本", "json", None),
}
FIELD_IDS = {key: identity("case:" + key) for key in FIELDS}
RESULT_TABLE_ID = identity("results")
RESULT_FIELDS = {
    "run": ("Run ID", "text", None), "task": ("Task ID", "text", None),
    "temperature": ("Temperature", "number", "K"), "step": ("Final step", "integer", None),
    "energy": ("Total energy (normalized)", "number", None),
    "program": ("Solver SHA-256", "text", None), "files": ("Result files", "json", None),
}
RESULT_FIELD_IDS = {key: identity("result:" + key) for key in RESULT_FIELDS}
LABEL = "MuFerro / "
MAX_INPUT_BYTES = 256 * 1024 * 1024


def _copy_input(source, target, remaining):
    """Bound source reads and reject replacement with a link, FIFO, or changing file."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(source, flags), "rb") as inp, target.open("xb") as out:
        before = os.fstat(inp.fileno())
        if not stat.S_ISREG(before.st_mode) or source.is_symlink() or before.st_size > remaining:
            raise ValueError("Input is not a regular file within the input budget")
        count = 0
        while True:
            block = inp.read(min(1024 * 1024, remaining - count + 1))
            if not block:
                break
            count += len(block)
            if count > remaining:
                raise ValueError("Case exceeds the 256 MiB input limit")
            out.write(block)
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if signature(before) != signature(os.fstat(inp.fileno())) or signature(before) != signature(source.lstat()):
            raise ValueError("Case input changed while importing; import a stable case directory")
    return count


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _table(model, table_id, fields, ids):
    table = next((t for t in model["tables"] if t["id"] == table_id), None)
    if table is not None:
        actual = {f["id"]: (f["type"], f.get("unit")) for f in table["fields"]}
        if any(actual.get(ids[key]) != (kind, unit) for key, (_, kind, unit) in fields.items()):
            raise ValueError("MuFerro table fields were removed or changed; restore their types before continuing")
    return table


def _create_table(table_id, name, fields, ids):
    return [{"op": "create_table", "id": table_id, "name": name}] + [
        {"op": "add_field", "id": ids[key], "table_id": table_id, "name": label, "type": kind,
         **({"unit": unit} if unit else {})} for key, (label, kind, unit) in fields.items()]


def _cells(table_id, row_id, values, ids):
    return [{"op": "set_cell", "table_id": table_id, "record_id": row_id,
             "field_id": ids[key], "value": value} for key, value in values.items()]


def _capture(project, paths, expected_hashes, revision):
    indexed = project.files.index(paths, expected_revision=revision)
    captured = project.snapshots.capture(indexed["record_ids"], expected_revision=indexed["revision"])
    actual = {f["record_id"]: f["sha256"] for f in captured["snapshot"]["manifest"]["files"]}
    if actual != dict(zip(indexed["record_ids"], expected_hashes)):
        raise ValueError("Input files changed between generation and freezing; no run was prepared")
    return indexed, captured


def _revision(project, expected):
    model = project.snapshot()
    if type(expected) is not int or model["project"]["revision"] != expected:
        raise ValueError("Project changed; refresh it and inspect the current parameters before continuing")
    return model


def _inputs(folder):
    """A deliberately explicit native input set; never traverse/copy a licence directory."""
    folder = Path(folder).expanduser().resolve(strict=True)
    paths, pending, size, visited = [], [folder], 0, 0
    while pending:
        for path in sorted(pending.pop().iterdir()):
            visited += 1
            if visited > 256:
                raise ValueError("Use a clean case directory with at most 100 input files and 256 entries")
            info = path.lstat()
            if path.name.lower() == "key" or path.suffix.lower() == ".lic":
                raise ValueError("Licence files must stay on the compute host, outside the case directory")
            if stat.S_ISLNK(info.st_mode):
                raise ValueError("Case inputs must be regular files, without symbolic links")
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
            elif stat.S_ISREG(info.st_mode) and path.suffix.lower() in {".toml", ".in"}:
                paths.append(path)
                size += info.st_size
            else:
                raise ValueError("Use a clean MuFerro input directory containing only .toml and .in files")
            if len(paths) > 100 or size > MAX_INPUT_BYTES:
                raise ValueError("Case exceeds 100 files or the 256 MiB input limit")
    if not (folder / "input.toml").is_file():
        raise ValueError("The case directory needs input.toml")
    return folder, sorted(paths)


def _document(folder):
    document = _toml_document(folder / "input.toml", folder)
    material = document.get("material")
    if not isinstance(material, str):
        raise ValueError("input.toml must name its material file")
    material = relative_path(material)
    if Path(material).suffix.lower() != ".toml":
        raise ValueError("The material input must be a TOML file")
    _toml_document(folder / material, folder, label="material")
    return document


def _parameters(values):
    for key in ("steps", "interval", "attempt"):
        if type(values[key]) is not int or values[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    for key in ("temperature", "dt"):
        if type(values[key]) not in (int, float) or not math.isfinite(values[key]) or values[key] <= 0:
            raise ValueError(f"{key} must be finite and positive")


def _restore(project, source, folder):
    if not isinstance(source, dict) or set(source) != {"snapshot_id", "bindings"}:
        raise ValueError("The case must reference its imported source snapshot and bindings")
    bindings = source["bindings"]
    if not isinstance(bindings, dict) or not 1 <= len(bindings) <= 100:
        raise ValueError("Invalid MuFerro input bindings")
    for name, record_id in bindings.items():
        name = relative_path(name)
        if Path(name).suffix.lower() not in {".toml", ".in"} or "key" in Path(name).parts:
            raise ValueError("Invalid MuFerro input filename")
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        resolved = project.snapshots.resolve(source["snapshot_id"], record_id)
        with path.open("xb") as out, Path(resolved["path"]).open("rb") as inp:
            shutil.copyfileobj(inp, out)
    return sorted(folder.rglob("*"))


def _directory(stk, project):
    info = next((p for p in stk.projects.list() if p["handle"] == project.handle), None)
    if info is None:
        raise ValueError("This project is no longer open")
    return Path(info["directory"])


def _folder(root, *parts):
    """Owned project output directories cannot redirect writes outside the project."""
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Workflow directories must not be symbolic links")
        path.mkdir(exist_ok=True)
    return path


class MuFerro:
    def __init__(self, stk):
        self.stk = stk

    def import_case(self, source, *, expected_revision, project=None):
        """Copy and freeze a clean native case; create one editable case row, without execution."""
        p = project or self.stk.project
        model = _revision(p, expected_revision)
        table = _table(model, TABLE_ID, FIELDS, FIELD_IDS)
        source, paths = _inputs(source)
        row_id = str(uuid4())
        root = _directory(self.stk, p)
        destination = _folder(root, "inputs", "muferro", row_id)
        copied, remaining = [], MAX_INPUT_BYTES
        for path in paths:
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            remaining -= _copy_input(path, target, remaining)
            copied.append(target)
        hashes = [_hash(path) for path in copied]
        # Read what was copied, not the mutable original; generated TOML must round-trip.
        doc = _document(destination)
        case = read_case(destination)
        check_case(case, destination, 1)
        values = {"name": source.name, "temperature": doc["system"].get("temperature"),
                  "steps": case["steps"], "dt": doc["system"].get("dt"),
                  "interval": case["output_interval"], "attempt": 1}
        _parameters(values)
        indexed, captured = _capture(p, copied, hashes, expected_revision)
        values["source"] = {"snapshot_id": captured["snapshot"]["id"], "bindings": dict(zip(
            [path.relative_to(destination).as_posix() for path in copied], indexed["record_ids"]))}
        commands = [] if table else _create_table(TABLE_ID, "MuFerro cases / 仿真参数", FIELDS, FIELD_IDS)
        commands += [{"op": "add_record", "id": row_id, "table_id": TABLE_ID}]
        commands += _cells(TABLE_ID, row_id, values, FIELD_IDS)
        result = p.apply(commands, expected_revision=captured["revision"])
        print("Imported MuFerro case:", row_id, "— edit its parameter row, then prepare", flush=True)
        return {"table_id": TABLE_ID, "record_id": row_id, "revision": result["revision"]}

    def prepare(self, record_id, connection, *, expected_revision, project=None, **options):
        """Freeze inputs and prepare one plan. Repeating the same row/options reuses that plan.

        Options are muferro_spec resource/node-environment options; workspace/input/name are owned
        by this workflow. Increment the row's Attempt field to request an independent rerun.
        """
        p = project or self.stk.project
        model = _revision(p, expected_revision)
        table = _table(model, TABLE_ID, FIELDS, FIELD_IDS)
        row = next((r for r in table["records"] if r["id"] == record_id), None) if table else None
        if row is None or any(e.get("state") != "ok" for e in row.get("evaluations", {}).values()):
            raise ValueError("Select a MuFerro case row without formula errors")
        values = {key: row["values"].get(field) for key, field in FIELD_IDS.items()}
        _parameters(values)
        if connection.startswith("hub:"):
            raise ValueError("MuFerro preparation currently uses direct/SSH Runtime profiles; Hub preparation is not supported")
        if set(options) & {"workspace_id", "case_dir", "inputs", "example", "name"}:
            raise ValueError("The MuFerro workflow owns workspace, input and task names")
        # Validate execution options before creating files or making network requests.
        template = muferro_spec("0" * 32, case_dir="case", name="MuFerro", **options)
        TaskSpec(**template)
        fingerprint = hashlib.sha256(_canonical({"project": model["project"]["id"], "record": record_id,
            "values": row["values"], "definitions": row.get("definitions", {}),
            "fields": {f["id"]: [f["type"], f.get("unit")] for f in table["fields"]},
            "connection": connection, "spec": template}).encode("utf-8")).hexdigest()
        label = LABEL + str(values["name"])[:40] + f" · {values['temperature']:g} K / " + fingerprint
        offset = 0
        while True:
            page = p.runs.list(offset=offset)
            for summary in page["runs"]:
                if summary["label"] == label:
                    run = p.runs.get(summary["id"])
                    if run["parameter_state"] != "current":
                        raise ValueError("Existing plan no longer matches these parameters; increment Attempt to prepare again")
                    p.runs.refresh(run["id"])  # also validates the saved endpoint fingerprint
                    print("Reusing prepared MuFerro run:", run["id"], flush=True)
                    return run
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        root = _directory(self.stk, p)
        with TemporaryDirectory(prefix="stk-muferro-") as scratch:
            folder = Path(scratch)
            _restore(p, values["source"], folder)
            doc = deepcopy(_document(folder))
            doc["system"].update(temperature=values["temperature"], timestep_total=values["steps"], dt=values["dt"])
            doc["output"]["interval"] = values["interval"]
            text = dump_toml(doc)
            if tomllib.loads(text) != doc:
                raise ValueError("Generated TOML does not preserve the original input types")
            (folder / "input.toml").write_text(text, encoding="utf-8", newline="\n")
            check_case(read_case(folder), folder, template["resources"]["ranks"])
            destination = _folder(root, "inputs", "muferro-prepared", fingerprint)
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
        key = "muferro:" + fingerprint
        workspace = runtime.workspaces.create("MuFerro " + fingerprint[:12], idempotency_key=key + ":workspace")["workspace"]["id"]
        for remote, file_id in bindings.items():
            source = p.snapshots.resolve(snapshot_id, file_id)["path"]
            transfer = runtime.upload(workspace, source, remote=remote,
                                      idempotency_key=key + ":input:" + hashlib.sha256(remote.encode()).hexdigest())
            self._transfer(transfer)
        # Runtime normally omits unchanged inputs from its artifact list. Explicitly publish
        # them so collection can check the exact bytes used by the solver as well as outputs.
        spec = {**template, "workspace_id": workspace, "outputs": ["stk-mupro.json", *bindings]}
        prepared = p.runs.prepare([{"table_id": TABLE_ID, "record_id": record_id, "label": label,
            "input_snapshot_id": snapshot_id, "input_bindings": bindings, "spec": spec}],
            connection=connection, expected_revision=captured["revision"])
        run = p.runs.get(prepared["run_ids"][0])
        print("Prepared MuFerro run:", run["id"], "— no task submitted; inspect and submit in Runs", flush=True)
        return run

    def _transfer(self, transfer):
        result = self.stk.transfers.wait(transfer["id"], timeout=300)
        if result["state"] != "completed":
            raise RuntimeError(f"Transfer {result['id']} is {result['state']}; inspect Transfers and explicitly resume if needed")

    def collect(self, run_id, *, project=None, max_bytes=1024**3):
        """Download and verify one successful run, then register a stable result row. Never submits."""
        p = project or self.stk.project
        run = p.runs.refresh(run_id)
        plan, status = run["plan"], run["status"]
        if not plan["label"].startswith(LABEL) or plan["parameters"]["table_id"] != TABLE_ID:
            raise ValueError("Select a run prepared by the MuFerro project workflow")
        task = status.get("task")
        if not task or task["state"] != "succeeded":
            raise ValueError("Collect requires a successfully finished task; inspect its state and logs")
        root = _directory(self.stk, p)
        destination = _folder(root, "results", "muferro", str(UUID(run_id)))
        runtime = self.stk.runtime(plan["connection"])
        artifacts = {item["path"]: item for item in runtime.tasks.artifacts(task["id"])}
        with TemporaryDirectory(prefix="stk-muferro-check-") as scratch:
            folder = Path(scratch)
            _restore(p, {"snapshot_id": plan["input_snapshot_id"], "bindings": {
                name.removeprefix("case/"): value for name, value in plan["input_bindings"].items()}}, folder)
            case = read_case(folder)
        names = sorted(set(plan["input_bindings"]) | {"stk-mupro.json"} |
                       {"case/" + name for name in (*RUN_OUTPUTS, *expected_frames(case))})
        if type(max_bytes) is not int or max_bytes <= 0 or len(names) > 10000:
            raise ValueError("Invalid download budget or more than 10000 result files")
        if any(name not in artifacts for name in names):
            raise ValueError("Successful task has missing MuFerro outputs or original inputs")
        if sum(artifacts[name]["size"] for name in names) > max_bytes or artifacts["stk-mupro.json"]["size"] > 2 * 1024 * 1024:
            raise ValueError("MuFerro results exceed the download budget")
        if any(artifacts[f["path"]]["sha256"] != f["sha256"] for f in plan["inputs"]):
            raise ValueError("Task input bytes do not match the frozen run plan")
        paths = []
        for name in names:
            path = destination / relative_path(name)
            _folder(destination, *Path(name).parts[:-1])
            if path.is_symlink():
                raise ValueError("Result paths must not be symbolic links")
            if not path.exists():
                transfer = runtime.download(name, task_id=task["id"], dest=path,
                    idempotency_key=f"muferro:{run_id}:result:" + hashlib.sha256(name.encode()).hexdigest())
                self._transfer(transfer)
            if not path.is_file() or path.stat().st_size != artifacts[name]["size"] or _hash(path) != artifacts[name]["sha256"]:
                raise ValueError(f"Result changed locally or was not downloaded: {name}; inspect Transfers before repairing")
            paths.append(path)
        report = json.loads((destination / "stk-mupro.json").read_text(encoding="utf-8"))
        verification = verify_run(destination, "case")
        if (report.get("app") != "muFerro" or report.get("state") != "succeeded" or report.get("case_dir") != "case"
                or report.get("verification", {}).get("verifier") != VERIFIER
                or report.get("verification", {}).get("status") != "passed"
                or verification["verification"]["status"] != "passed" or verification["qoi"] != report.get("qoi")
                or report.get("case") != case):
            raise ValueError("Collected MuFerro output does not match its input/completion/energy contract")
        revision = p.snapshot()["project"]["revision"]
        for offset in range(0, len(paths), 100):
            revision = p.files.index(paths[offset:offset + 100], expected_revision=revision)["revision"]
        model = _revision(p, revision)
        table = _table(model, RESULT_TABLE_ID, RESULT_FIELDS, RESULT_FIELD_IDS)
        commands = [] if table else _create_table(RESULT_TABLE_ID, "MuFerro results / 仿真结果", RESULT_FIELDS, RESULT_FIELD_IDS)
        row_id = str(uuid5(UUID(run_id), "muferro-result"))
        if table is None or not any(r["id"] == row_id for r in table["records"]):
            commands.append({"op": "add_record", "id": row_id, "table_id": RESULT_TABLE_ID})
        values = {"run": run_id, "task": task["id"], "temperature": plan["parameters"]["values"][FIELD_IDS["temperature"]],
                  "step": verification["qoi"]["step"], "energy": verification["qoi"]["total_energy"],
                  "program": report.get("program", {}).get("sha256"),
                  "files": [{"path": path.relative_to(root).as_posix(), "sha256": artifacts[name]["sha256"]}
                            for name, path in zip(names, paths)]}
        commands += _cells(RESULT_TABLE_ID, row_id, values, RESULT_FIELD_IDS)
        p.apply(commands, expected_revision=revision)
        print("Collected MuFerro run:", run_id, "— final energy:", values["energy"], flush=True)
        return {"run_id": run_id, "table_id": RESULT_TABLE_ID, "record_id": row_id,
                "directory": str(destination / "case"), "qoi": verification["qoi"], "files": values["files"]}

    def view(self, run_id, *, project=None):
        """Recheck collected bytes and open the domain view; does not download or submit work."""
        p = project or self.stk.project
        model = p.snapshot()
        table = _table(model, RESULT_TABLE_ID, RESULT_FIELDS, RESULT_FIELD_IDS)
        row_id = str(uuid5(UUID(run_id), "muferro-result"))
        row = next((r for r in table["records"] if r["id"] == row_id), None) if table else None
        if row is None:
            raise ValueError("Collect this MuFerro run before viewing it")
        root = _directory(self.stk, p)
        for file in row["values"][RESULT_FIELD_IDS["files"]]:
            path = root / relative_path(file["path"])
            if not path.resolve().is_relative_to(root.resolve()) or _hash(path) != file["sha256"]:
                raise ValueError("Collected result changed locally; inspect its files before viewing")
        folder = root / "results" / "muferro" / str(UUID(run_id)) / "case"
        return self.stk.viewer.open(folder, preset="muferro-domains")


def native_action(stk, action, params):
    """Fixed native button entry point; data is JSON, never interpolated executable Python."""
    params = dict(params)
    p = stk.project
    if p.snapshot()["project"]["id"] != params.pop("project_id"):
        raise ValueError("The selected project changed; inspect the current project before continuing")
    if action == "import":
        return stk.muferro.import_case(project=p, **params)
    if action == "prepare":
        options = params.pop("options", {})
        return stk.muferro.prepare(project=p, **params, **options)
    if action == "collect":
        return stk.muferro.collect(project=p, **params)
    if action == "view":
        return stk.muferro.view(project=p, **params)
    if action == "logs":
        run = p.runs.refresh(params["run_id"])
        task = run["status"].get("task")
        if not task:
            raise ValueError("This run has not been accepted by the Runtime")
        runtime = stk.runtime(run["plan"]["connection"], node=run["plan"]["node"])
        for stream in ("stdout", "stderr"):
            print(f"MuFerro {run['id']} — {stream} (first 64 KiB)", flush=True)
            print(runtime.tasks.logs(task["id"], stream=stream)["data"].decode("utf-8", errors="replace"), flush=True)
        return None
    raise ValueError("Unknown MuFerro workflow action")
