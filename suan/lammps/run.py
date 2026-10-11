"""Compute-side LAMMPS launcher, per-run verifier and node check.

`python -m suan.lammps run` executes inside the task work dir (its CWD). It reads the case's
``stk-lammps-input.json`` (script name and parameter values, written when the run was prepared), checks the
script again, finds the LAMMPS program (``--program``, else the STK module registry on this computer, else
``lmp``/``lmp_mpi``/``lmp_serial`` on PATH), runs ``lmp -in <script> -log log.lammps -nocite -var name value ...``
in the case folder and checks ``log.lammps``, writing ``stk-lammps.json``. Exit 0 from LAMMPS alone never
means success: the log must end normally with finite thermodynamic output.

Several ranks use mpiexec (MPICH's from the same conda environment is found first), with the same local-MPI
guard as MuPRO (suan/runtime/launch.py).
"""

from pathlib import Path
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys

from suan.monitor.events import ENV_PATH as MONITOR_ENV
from suan.runtime.common import atomic_json, now, sha256
from suan.runtime.launch import LAUNCHERS, mpi_command
from suan.runtime.models import relative_path
from .log import MAX_LOG_BYTES, VERIFIER, verify_log
from .script import OWN_FILES, ScriptError, check_parameters, check_script, format_value

RESULT = "stk-lammps.json"
INPUT = "stk-lammps-input.json"
INPUT_FORMAT = "stk.lammps-input/1"
LOG = "log.lammps"
PROGRAMS = ("lmp", "lmp_mpi", "lmp_serial")
MAX_OUTPUTS = 1000
ENVIRONMENT = ("OMP_NUM_THREADS", "SRUN_CPUS_PER_TASK")


class LammpsError(ValueError):
    def __init__(self, message, classification="configuration"):
        super().__init__(message)
        self.classification = classification


def _case_folder(work, case_dir):
    try:
        case_dir = "." if case_dir == "." else relative_path(case_dir)
    except ValueError as exc:
        raise LammpsError(f"Invalid case directory: {exc}") from exc
    folder = (work / case_dir).resolve()
    if folder != work and work not in folder.parents:
        raise LammpsError("The case directory must stay inside the task work directory")
    return case_dir, folder


def case_files(folder):
    """The case's files (POSIX names relative to the folder), without symbolic links."""
    names = []
    for path in sorted(Path(folder).rglob("*")):
        if path.is_symlink():
            raise LammpsError("Case files must not be symbolic links")
        if path.is_file():
            names.append(path.relative_to(folder).as_posix())
    return names


def read_input(folder):
    """The prepared run: {script, variables, used, units}; the script is checked as on import."""
    try:
        document = json.loads((folder / INPUT).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LammpsError(f"Cannot read {INPUT}: {exc}") from exc
    if not isinstance(document, dict) or document.get("format") != INPUT_FORMAT or \
            not isinstance(document.get("script"), str) or not isinstance(document.get("variables"), dict):
        raise LammpsError(f"{INPUT} is not a prepared STK LAMMPS input")
    files = case_files(folder)
    try:
        script = relative_path(document["script"])
        if script not in files:
            raise LammpsError(f"The input script {script} is not in the case")
        checked = check_script((folder / script).read_text(encoding="utf-8"), files,
                               lambda name: (folder / name).read_text(encoding="utf-8"))
        variables = check_parameters(document["variables"], checked["used"])
    except (ScriptError, UnicodeDecodeError, ValueError) as exc:
        if isinstance(exc, LammpsError):
            raise
        raise LammpsError(f"Input script: {exc}") from exc
    stale = sorted((OWN_FILES - {INPUT}) & set(files))
    if stale:
        raise LammpsError("The case already holds LAMMPS outputs (" + ", ".join(stale) + "); use a clean case")
    return {"script": script, "variables": variables, "used": checked["used"], "units": checked["units"]}


def resolve_program(program, env):
    if program and (os.sep in program or "/" in program):
        path = Path(os.path.abspath(program))
    elif program:
        found = shutil.which(program, path=env.get("PATH", ""))
        if not found:
            raise LammpsError(f"LAMMPS program {program} not found on PATH")
        path = Path(found)
    else:
        try:
            from suan.modules import find_program
            registered = find_program("lammps")
        except Exception:  # noqa: BLE001 - a damaged registry falls back to PATH
            registered = None
        found = registered or next((p for p in (shutil.which(name, path=env.get("PATH", "")) for name in PROGRAMS) if p), None)
        if not found:
            raise LammpsError("LAMMPS was not found: install the LAMMPS module in STK, put lmp on PATH or pass --program")
        path = Path(found)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise LammpsError(f"LAMMPS program is not an executable file: {path}")
    return path.absolute()


def has_mpi(program, env):
    """Whether ``lmp -h`` reports a real MPI library (a build without MPI reports 'LAMMPS MPI STUBS')."""
    try:
        completed = subprocess.run([str(program), "-h"], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   errors="replace", timeout=60, env=env, cwd=str(program.parent))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LammpsError(f"Cannot run {program} -h: {exc}") from exc
    lines = [line for line in completed.stdout.splitlines() if line.startswith("MPI v")]
    if not lines:
        raise LammpsError(f"{program} -h does not report its MPI library; is it LAMMPS?")
    return "MPI STUBS" not in lines[0]


def _outputs(folder, inputs, prefix):
    """Files the run wrote in the case folder, with sizes and digests (at most 1000). A run that changed one of
    its inputs cannot be checked against its frozen plan, so that fails."""
    items = []
    for name in case_files(folder):
        digest = sha256(folder / name)
        if name in inputs and inputs[name] != digest:
            raise LammpsError(f"The script overwrote its input {name}; write results to a new file name", "invalid_result")
        if inputs.get(name) != digest:
            items.append({"path": prefix + name, "size": (folder / name).stat().st_size, "sha256": digest})
            if len(items) >= MAX_OUTPUTS:
                break
    return items


def _read_log(path):
    try:
        if path.stat().st_size > MAX_LOG_BYTES:
            raise LammpsError("log.lammps exceeds 256 MiB; lower the thermo output frequency", "invalid_result")
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _stopped(signum, frame):
    raise LammpsError(f"Stopped by signal {signum} (cancelled, walltime or memory limit)", "cancelled")


def run(args):
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stopped)  # the record below is still written; subprocess.run kills LAMMPS
    work = Path.cwd().resolve()
    record = {"schema_version": 1, "app": "LAMMPS", "state": "running", "classification": None, "reason": "",
              "case_dir": args.case_dir, "script": None, "variables": None, "units": None, "version": None,
              "layout": {"ranks": args.ranks, "threads_per_rank": args.threads_per_rank, "launcher": None},
              "command": [], "program": {"path": None, "sha256": None},
              "environment": {key: None for key in ENVIRONMENT}, "exit_code": None,
              "started_at": now(), "finished_at": None,
              "verification": {"verifier": VERIFIER, "status": "not_run", "checks": []}, "qoi": None,
              "warnings": [], "outputs": []}
    try:
        case_dir, folder = _case_folder(work, args.case_dir)
        record["case_dir"] = case_dir
        if not folder.is_dir():
            raise LammpsError(f"Case directory not found: {case_dir}")
        prepared = read_input(folder)
        record.update(script=prepared["script"], variables=prepared["variables"], units=prepared["units"])
        env = os.environ.copy()
        env.pop(MONITOR_ENV, None)
        program = resolve_program(args.program, env)
        # A conda environment's own MPI launcher sits next to its lmp.
        env["PATH"] = str(program.parent) + os.pathsep + env.get("PATH", "")
        env["OMP_NUM_THREADS"] = str(args.threads_per_rank)
        if args.ranks > 1 and not has_mpi(program, env):
            raise LammpsError("This LAMMPS was built without MPI (MPI STUBS): several ranks would each run the whole "
                              "case. Run one rank, or install the STK LAMMPS module (built with MPICH)")
        launcher, command = mpi_command(program, args.ranks, args.threads_per_rank, args.launcher, env,
                                        error=LammpsError, missing_hint="install MPI with LAMMPS or load the site's MPI")
        command += ["-in", prepared["script"], "-log", "log.lammps", "-nocite"]
        for name, value in prepared["variables"].items():
            command += ["-var", name, format_value(value)]
        try:
            digest = sha256(program)
        except OSError as exc:
            raise LammpsError(f"Cannot read the LAMMPS program: {exc}") from exc
        record["layout"]["launcher"] = launcher
        record.update(command=command, program={"path": str(program), "sha256": digest},
                      environment={key: env.get(key) for key in ENVIRONMENT})
        inputs = {name: sha256(folder / name) for name in case_files(folder)}
        atomic_json(work / RESULT, record)
        try:
            completed = subprocess.run(command, cwd=folder, env=env, stdin=subprocess.DEVNULL)
        except OSError as exc:
            raise LammpsError(f"Cannot start {command[0]}: {exc}", "launch_failed") from exc
        record["exit_code"] = completed.returncode
        prefix = "" if case_dir == "." else case_dir + "/"
        checked = verify_log(_read_log(folder / LOG), completed.returncode)
        record.update(verification=checked["verification"], qoi=checked["qoi"], warnings=checked["warnings"],
                      version=checked["version"], units=checked["units"] or record["units"])
        if completed.returncode:
            raise LammpsError(f"LAMMPS exited with code {completed.returncode}"
                              + (f": {checked['reason']}" if checked["reason"] else "; inspect stdout.log and log.lammps"),
                              "solver_failed")
        record["outputs"] = _outputs(folder, inputs, prefix)
        record.update(classification=checked["classification"], reason=checked["reason"])
        record["state"] = "succeeded" if checked["verification"]["status"] == "passed" else "failed"
    except LammpsError as exc:
        record.update(state="failed", classification=exc.classification, reason=str(exc))
    except Exception as exc:  # Last resort: the task must still get its stk-lammps.json.
        record.update(state="failed", classification="configuration", reason=f"{type(exc).__name__}: {exc}")
    record["finished_at"] = now()
    atomic_json(work / RESULT, record)
    if record["state"] == "succeeded":
        density = record["qoi"].get("density")
        print("LAMMPS succeeded: log verified" + (f", mean density {density:.4g}" if density is not None else ""))
        return 0
    print(f"LAMMPS failed ({record['classification']}): {record['reason']}", file=sys.stderr)
    # 2: configuration or launch failure, LAMMPS did not run; 3: it ran and failed or did not verify.
    return 2 if record["exit_code"] is None else 3


def verify(args):
    work = Path(args.work).resolve()
    _, folder = _case_folder(work, args.case_dir)
    result = verify_log(_read_log(folder / LOG))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in result["verification"]["checks"]:
            print(f"[{item['status'].upper()}] {item['id']}: {item['message']}")
        print(f"Verification {result['verification']['status']}"
              + (f" ({result['classification']}): {result['reason']}" if result["classification"] else ""))
    return 0 if result["verification"]["status"] == "passed" else 3


def packages(help_text):
    """The package names listed under 'Installed packages:' in ``lmp -h``."""
    lines, names = help_text.splitlines(), []
    if "Installed packages:" not in lines:
        return names
    for line in lines[lines.index("Installed packages:") + 1:]:
        if not line.strip():
            if names:
                break
            continue
        names += line.split()
    return names


def check(args):
    """Diagnose this node's LAMMPS: program, version, the packages molecular models need, and MPI."""
    checks = []

    def add(check_id, status, message):
        checks.append({"id": check_id, "status": status, "message": message})

    env = os.environ.copy()
    program = None
    try:
        program = resolve_program(args.program, env)
        add("program", "pass", str(program))
    except LammpsError as exc:
        add("program", "fail", str(exc))
    if program:
        try:
            completed = subprocess.run([str(program), "-h"], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                       errors="replace", timeout=60, cwd=str(program.parent))
            text = completed.stdout
            version = next((line.split(" - ", 1)[1].strip() for line in text.splitlines()
                            if "Simulator - " in line), None)
            add("version", "pass" if version else "warn", version or "LAMMPS did not print its version")
            mpi = next((line for line in text.splitlines() if line.startswith("MPI v")), "")
            add("mpi_library", "warn" if not mpi or "MPI STUBS" in mpi else "pass",
                "Built without MPI: one rank only" if "MPI STUBS" in mpi else mpi[:200] or "No MPI line in lmp -h")
            found = set(packages(text))
            missing = [name for name in ("MOLECULE", "KSPACE") if name not in found]
            add("packages", "warn" if missing else "pass",
                ("Missing packages for molecular models: " + ", ".join(missing)) if missing
                else "MOLECULE and KSPACE are installed")
        except (OSError, subprocess.TimeoutExpired) as exc:
            add("version", "fail", f"Cannot run {program} -h: {exc}")
    launcher = shutil.which("mpiexec", path=(str(program.parent) + os.pathsep if program else "") + env.get("PATH", ""))
    add("mpi_launcher", "pass" if launcher else "warn", launcher or "mpiexec not found; LAMMPS runs one rank")
    report = {"ok": not any(item["status"] == "fail" for item in checks), "checks": checks}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in checks:
            print(f"[{item['status'].upper()}] {item['id']}: {item['message']}")
    return 0 if report["ok"] else 1


def _positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m suan.lammps", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    launch = commands.add_parser("run", help="Run a prepared LAMMPS case in the task work dir and verify its log.")
    launch.add_argument("--program", help="LAMMPS executable name on PATH or path (default: the STK module, then lmp).")
    launch.add_argument("--case-dir", default=".", help="Case directory relative to the work dir.")
    launch.add_argument("--ranks", type=_positive, default=1, help="Total MPI ranks.")
    launch.add_argument("--threads-per-rank", type=_positive, default=1, help="OpenMP threads per rank.")
    launch.add_argument("--launcher", choices=LAUNCHERS, default="auto", help="auto: direct for 1 rank, else mpiexec.")
    launch.set_defaults(handler=run)
    audit = commands.add_parser("verify", help="Check a finished case's log.lammps.")
    audit.add_argument("--work", default=".", help="Task work dir.")
    audit.add_argument("--case-dir", default=".", help="Case directory relative to the work dir.")
    audit.add_argument("--json", action="store_true")
    audit.set_defaults(handler=verify)
    doctor = commands.add_parser("check", help="Diagnose this node's LAMMPS.")
    doctor.add_argument("--program")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(handler=check)
    args = parser.parse_args(argv)
    return args.handler(args)
