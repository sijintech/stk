"""Local PET modeling, isolated in the optional molecular-modeling environment.

Project workflows freeze the table parameters before this explicitly started step.
Its complete case folder is published once and its files are then snapshotted by
the ordinary workflow executor. Import that folder as a LAMMPS case explicitly;
the current remote LAMMPS template does not consume modeling-step files.
"""
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

from suan.lammps.pet import DEFAULT_PARAMETERS, OUTPUTS, PROFILE_ID
from suan.project import ProjectError
from .common import _cells, _create_table, _revision


FIELDS = {
    "chain_length": ("Chain length / 链长", "integer", None),
    "chain_count": ("Chain count / 链数", "integer", None),
    "packing_density": ("Initial packing density / 初始填充密度", "number", "kg/m3"),
    "seed": ("Random seed / 随机种子", "integer", None),
}
MAX_OUTPUT_BYTES = 256 * 1024 * 1024
MAX_LOG_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
ERROR_TAIL_BYTES = 8192
TIMEOUT_SECONDS = 1800
# Modeling is local and offline. Only these ordinary operating-system settings
# reach its Python/Packmol processes; credentials, proxies and model settings do not.
_ENVIRONMENT = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP",
                "SYSTEMROOT", "SYSTEMDRIVE", "USERPROFILE", "COMSPEC", "PATHEXT", "WINDIR")
_BOOTSTRAP = ("import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); "
              "runpy.run_module('suan.lammps.pet_worker',run_name='__main__')")


class ModelingCancelled(ProjectError):
    """The local modeling process was stopped before publishing its outputs."""


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise ModelingCancelled("PET modeling was cancelled")


def _program(module, name):
    from suan.modules import find_program
    found = find_program(module, name)
    if not found:
        raise ProjectError(f"PET modeling needs the {module} module; detect or install it in Compute modules")
    path = Path(found).absolute()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ProjectError(f"The registered {module} program is unavailable; detect it again in Compute modules")
    return path


def _environment(python, packmol):
    env = {key: os.environ[key] for key in _ENVIRONMENT if key in os.environ}
    folders = [python.parent, packmol.parent]
    if os.name == "nt":
        folders += [python.parent / "Scripts", python.parent / "Library" / "bin"]
    env["PATH"] = os.pathsep.join([*(str(folder) for folder in folders),
                                  *([env["PATH"]] if env.get("PATH") else [])])
    return env


def _stop(process):
    """Stop Python and Packmol before deleting their staging directory."""
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        import psutil
        children = set()
        try:
            tree = psutil.Process(process.pid)
            tree.suspend()
            for _ in range(2):
                for child in tree.children(recursive=True):
                    children.add(child)
                    try:
                        child.suspend()
                    except psutil.NoSuchProcess:
                        pass
        except psutil.NoSuchProcess:
            pass
        for child in children:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        if process.poll() is None:
            process.kill()
        psutil.wait_procs(children, timeout=3)
    process.wait(timeout=5)


def _tail(path):
    with Path(path).open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - ERROR_TAIL_BYTES))
        return stream.read(ERROR_TAIL_BYTES).decode("utf-8", errors="replace").strip()


def _publish(source, destination):
    """Atomic directory rename that never replaces an existing destination.

    Plain POSIX rename would replace an empty directory created by another
    process during modeling. Require the operating system's exclusive variant.
    Linux: man7.org/linux/man-pages/man2/rename.2.html (RENAME_NOREPLACE).
    macOS: apple-oss-distributions/xnu, bsd/sys/stdio.h (RENAME_EXCL).
    """
    if os.name == "nt":
        os.rename(source, destination)  # Windows rename refuses an existing destination.
        return
    libc = ctypes.CDLL(None, use_errno=True)
    old, new = os.fsencode(source), os.fsencode(destination)
    if sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        operation = libc.renameat2
        operation.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        operation.restype = ctypes.c_int
        result = operation(-100, old, -100, new, 1)
    elif sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        operation = libc.renamex_np
        operation.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        operation.restype = ctypes.c_int
        result = operation(old, new, 4)
    else:
        raise ProjectError("This system cannot publish PET outputs atomically without replacing an existing directory")
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def _manifest(path):
    """Strict finite JSON, bounded before decoding; errors never echo its contents."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non-finite number")
        return number

    def invalid_constant(value):
        raise ValueError("non-finite constant")

    with path.open("rb") as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ProjectError("The PET model manifest exceeds its 2 MiB limit")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                           parse_float=finite_float, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise ProjectError("The PET model manifest must be finite UTF-8 JSON with unique keys") from None
    if type(value) is not dict:
        raise ProjectError("The PET model manifest must be a JSON object")
    return value


def _digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def _outputs(directory, parameters):
    if not directory.is_dir() or directory.is_symlink():
        raise ProjectError("The PET worker did not produce a regular case directory")
    paths = list(directory.iterdir())
    if {path.name for path in paths} != set(OUTPUTS):
        raise ProjectError("The PET worker did not produce exactly the declared case files")
    size = 0
    for path in paths:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
            raise ProjectError("PET outputs must be nonempty regular files, without symbolic links")
        size += info.st_size
    if size > MAX_OUTPUT_BYTES:
        raise ProjectError("The PET model exceeds the 256 MiB case limit")
    manifest = _manifest(directory / "pet-model.json")
    if manifest.get("format") != "stk.pet-model/1" or manifest.get("profile_id") != PROFILE_ID:
        raise ProjectError("The PET worker reported an unsupported model/profile version")
    reported = manifest.get("parameters")
    if (type(reported) is not dict or set(reported) != set(parameters)
            or any(type(reported[key]) is not type(value) or reported[key] != value
                   for key, value in parameters.items())):
        raise ProjectError("The PET worker report does not match the frozen modeling parameters")
    from suan.lammps.pet import forcefield_text, profile
    expected_profile = json.dumps(profile(), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                  allow_nan=False).encode("utf-8")
    try:
        actual_profile = json.dumps(manifest.get("forcefield"), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                    allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise ProjectError("The PET model report must contain the complete valid force-field profile") from None
    profile_digest = hashlib.sha256(expected_profile).hexdigest()
    if actual_profile != expected_profile or manifest.get("profile_canonical_sha256") != profile_digest:
        raise ProjectError("The PET worker report differs from the complete shipped force-field profile")
    files = {name: _digest(directory / name) for name in OUTPUTS if name != "pet-model.json"}
    if manifest.get("files") != files:
        raise ProjectError("The PET model manifest does not match all seven actual artifact hashes")
    expected_xml = hashlib.sha256(forcefield_text().encode("utf-8")).hexdigest()
    if manifest.get("forcefield_xml_sha256") != files["forcefield.xml"] or files["forcefield.xml"] != expected_xml:
        raise ProjectError("The PET force-field XML does not match the shipped resource and recorded hash")
    validation = manifest.get("validation")
    length, count = parameters["chain_length"], parameters["chain_count"]
    formula = {"C": 10 * length, "H": 8 * length + 2, "O": 4 * length + 1}
    if (type(validation) is not dict or type(validation.get("atoms")) is not int
            or validation["atoms"] != (22 * length + 3) * count
            or type(validation.get("chain_count")) is not int or validation["chain_count"] != count
            or type(validation.get("formula_per_chain")) is not dict
            or any(type(value) is not int for value in validation["formula_per_chain"].values())
            or validation["formula_per_chain"] != formula):
        raise ProjectError("The PET model report has an inconsistent chain count or COOH/OH formula")
    charges = validation.get("chain_charge_e")
    if type(charges) is not list or len(charges) != count:
        raise ProjectError("The PET model report must verify every chain charge")
    for charge in charges:
        try:
            valid = type(charge) in (int, float) and math.isfinite(charge) and abs(charge) <= 1e-10
        except OverflowError:
            valid = False
        if not valid:
            raise ProjectError("The PET model report must contain finite neutral charges for every chain")


def model_pet(parameters, directory, *, cancel=None, timeout=TIMEOUT_SECONDS):
    """Build one fresh case using detected modules, with no network or model request.

    Every output is staged next to ``directory`` and the complete directory is
    published atomically only after success. Existing destinations are preserved.
    """
    from suan.lammps.pet import validate_parameters
    parameters = validate_parameters(parameters)
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= TIMEOUT_SECONDS:
        raise ProjectError("PET modeling timeout must be positive and at most 1800 seconds")
    _check_cancel(cancel)
    destination = Path(directory).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ProjectError("PET modeling requires a new output directory")
    python = _program("molecular-modeling", "python")
    packmol = _program("packmol", "packmol")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Resolve the caller's parent once; publishing cannot follow a destination link.
    destination = destination.parent.resolve(strict=True) / destination.name
    if destination.exists() or destination.is_symlink():
        raise ProjectError("PET modeling requires a new output directory")
    with tempfile.TemporaryDirectory(prefix=".stk-pet-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        config, output, log = stage / "parameters.json", stage / "case", stage / "worker.log"
        config.write_text(json.dumps(parameters, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        root = Path(__file__).resolve().parents[2]
        argv = [str(python), "-I", "-c", _BOOTSTRAP, str(root),
                "--parameters", str(config), "--out", str(output), "--packmol", str(packmol)]
        process = None
        try:
            with log.open("wb") as stream:
                try:
                    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                                               cwd=stage, env=_environment(python, packmol),
                                               start_new_session=os.name != "nt")
                except OSError as error:
                    raise ProjectError(f"The PET modeling worker could not start: {error.strerror}") from None
                deadline = time.monotonic() + timeout
                while process.poll() is None:
                    _check_cancel(cancel)
                    if time.monotonic() >= deadline:
                        raise ProjectError("PET modeling exceeded its time budget")
                    if log.stat().st_size > MAX_LOG_BYTES:
                        raise ProjectError("PET modeling output exceeded its 8 MiB log limit")
                    if cancel is not None:
                        cancel.wait(0.05)
                    else:
                        time.sleep(0.05)
            _check_cancel(cancel)
            if process.returncode != 0:
                raise ProjectError(f"PET modeling exited with {process.returncode}: {_tail(log)}")
            if log.stat().st_size > MAX_LOG_BYTES:
                raise ProjectError("PET modeling output exceeded its 8 MiB log limit")
            _outputs(output, parameters)
            _check_cancel(cancel)
            _publish(output, destination)
        except BaseException:
            # A worker can exit while one of its descendants is still running.
            # Cancellation/failure must stop that group even after its leader exits.
            if process is not None:
                _stop(process)
            raise
        finally:
            if process is not None and process.poll() is None:
                _stop(process)
    return destination


def workflow_document(table_id, field_ids):
    """Ordinary parameter table → local PET modeling, without a Runtime step."""
    return {"format": "stk.workflow/1", "steps": [
        {"id": "cases", "kind": "table", "ref": {"table": table_id}},
        {"id": "model", "kind": "simulation", "ref": {"template": "pet-model/1"},
         "inputs": {"rows": {"from": "cases.rows"}},
         "parameters": {key: {"$field": field_ids[key]} for key in FIELDS}},
    ], "ui": {"positions": {"cases": [0, 0], "model": [260, 0]}}}


def create_pet_workflow(stk, *, expected_revision, rows=None, project=None, name="PET modeling / PET 建模"):
    """Create a parameter table and a saved local modeling workflow; execute nothing.

    ``rows`` is a list of 1–100 parameter dictionaries. Omitted parameters take
    the template defaults. The returned IDs remain the editable project objects;
    explicit preparation/start makes a separate immutable run.
    """
    from suan.lammps.pet import validate_parameters
    from suan.project.managed import name as valid_name
    name = valid_name(name, "Workflow")
    rows = [dict(DEFAULT_PARAMETERS)] if rows is None else rows
    if type(rows) is not list or not 1 <= len(rows) <= 100 or any(type(row) is not dict for row in rows):
        raise ProjectError("A PET modeling workflow needs 1 to 100 parameter dictionaries")
    normalized = [validate_parameters({**DEFAULT_PARAMETERS, **row}) for row in rows]
    p = project or stk.project
    _revision(p, expected_revision)
    table_id, workflow_id = str(uuid4()), str(uuid4())
    field_ids = {key: str(uuid4()) for key in FIELDS}
    record_ids = [str(uuid4()) for _ in normalized]
    commands = _create_table(table_id, "PET model parameters / PET 建模参数", FIELDS, field_ids)
    for record, parameters in zip(record_ids, normalized):
        commands.append({"op": "add_record", "id": record, "table_id": table_id})
        commands += _cells(table_id, record, parameters, field_ids)
    revision = p.apply(commands, expected_revision=expected_revision)["revision"]
    written = p.workflows.create(name, workflow_document(table_id, field_ids), workflow_id=workflow_id,
                                 expected_revision=revision)
    return {"table_id": table_id, "field_ids": field_ids, "record_ids": record_ids,
            "workflow_id": workflow_id, "revision": written["revision"]}


__all__ = ["DEFAULT_PARAMETERS", "OUTPUTS", "ModelingCancelled", "create_pet_workflow", "model_pet", "workflow_document"]
